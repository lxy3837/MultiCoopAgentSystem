"""
流程图解析模块

支持从 Mermaid 和 D2 流程图语法中解析出 Flow 对象，
用于 FLOW 类型技能的流程定义。
"""
from __future__ import annotations

import re

from skills.base import Flow, FlowNode, FlowEdge

from utils.logger import get_logger

logger = get_logger("skills.flow")


def parse_mermaid(mermaid_text: str) -> Flow:
    """解析 Mermaid flowchart 语法为 Flow 对象

    支持标准 Mermaid flowchart LR/TD 语法：
    - 矩形节点: A[Label]
    - 菱形决策节点: B{Label}
    - 圆角起止节点: C((Label))
    - 实线箭头: A --> B
    - 带标签箭头: A -->|condition| B

    Args:
        mermaid_text: Mermaid flowchart 文本（不含 ```mermaid 标记）

    Returns:
        解析后的 Flow 对象

    Raises:
        ValueError: 解析失败时抛出
    """
    mermaid_text = mermaid_text.strip()

    # 解析图表方向声明
    direction_match = re.match(r'^\s*(flowchart|graph)\s+(LR|TD|TB|RL|BT)\s*\n', mermaid_text, re.IGNORECASE)
    if direction_match:
        mermaid_text = mermaid_text[direction_match.end():]

    nodes: list[FlowNode] = []
    edges: list[FlowEdge] = []
    node_map: dict[str, FlowNode] = {}

    lines = [line.strip() for line in mermaid_text.split('\n') if line.strip()]

    for line in lines:
        # 行中可能同时包含节点定义和边，先提取节点再提取边
        parsed_any = False

        # 先提取行中所有节点定义
        for node_match in re.finditer(
            r'(\w+)(\{.+?\}|\[.+?\]|\(\(.+?\)\)|\(\[.+?\]\))', line
        ):
            node_text = node_match.group(0)  # e.g. "A[Label]"
            node = _parse_mermaid_node(node_text)
            if node and node.id not in node_map:
                nodes.append(node)
                node_map[node.id] = node
                parsed_any = True

        # 再提取行中的所有边
        # 将行按箭头分割：A --> B -->|label| C
        parts = re.split(r'(\s*-+>\s*(?:\|.+?\|\s*)?)', line)
        # parts alternates: [source, arrow, target, arrow, target, ...]
        edge_parts = parts[1:]  # skip the leading text before first arrow

        for i in range(0, len(edge_parts) - 1, 2):
            arrow = edge_parts[i]
            target_part = edge_parts[i + 1] if i + 1 < len(edge_parts) else ""

            # 找到 source（从当前箭头之前的 token）
            if i == 0:
                source_part = parts[0].strip()
            else:
                source_part = parts[i].strip()  # target of previous edge

            # 解析 source node ID
            source_id_match = re.match(r'(\w+)', source_part)
            # 解析 target node ID
            target_id_match = re.match(r'(\w+)', target_part)

            if source_id_match and target_id_match:
                source_id = source_id_match.group(1)
                target_id = target_id_match.group(1)

                # 从箭头中提取标签
                label_match = re.search(r'\|(.+?)\|', arrow)
                label = label_match.group(1).strip() if label_match else ""

                edge = FlowEdge(
                    from_id=source_id,
                    to_id=target_id,
                    label=label,
                )
                edges.append(edge)
                parsed_any = True

        if not parsed_any:
            logger.debug(f"无法识别的 Mermaid 行: {line}")

    if not nodes:
        raise ValueError("Mermaid 解析失败：未找到任何节点定义")

    # 自动检测起始和结束节点
    start_id, end_id = _detect_start_end(nodes)

    # 如果检测不到，取第一个节点作为开始，最后一个作为结束
    if not start_id and nodes:
        start_id = nodes[0].id
    if not end_id and nodes:
        end_id = nodes[-1].id

    return Flow(
        name="",
        nodes=nodes,
        edges=edges,
        start_id=start_id,
        end_id=end_id,
    )


def parse_d2(d2_text: str) -> Flow:
    """解析 D2 图表语法为 Flow 对象

    支持基本 D2 语法：
    - 节点: name: Label { shape: rectangle }
    - 连接: a -> b
    - 带标签连接: a -> b: label

    Args:
        d2_text: D2 图表文本（不含 ```d2 标记）

    Returns:
        解析后的 Flow 对象

    Raises:
        ValueError: 解析失败时抛出
    """
    d2_text = d2_text.strip()

    nodes: list[FlowNode] = []
    edges: list[FlowEdge] = []
    node_map: dict[str, FlowNode] = {}
    node_labels: dict[str, str] = {}
    node_types: dict[str, str] = {}

    # 第一遍：收集节点定义（带 shape 的块）
    lines = d2_text.split('\n')

    current_node_id: str | None = None
    in_node_block = False

    for line in lines:
        line = line.rstrip()

        # 节点定义开始: name: Label {
        node_start = re.match(r'^(\w+):\s*(.*?)\s*\{?\s*$', line)
        if node_start and not in_node_block:
            current_node_id = node_start.group(1)
            label = node_start.group(2) or current_node_id
            node_labels[current_node_id] = label.strip()
            if '{' in line:
                in_node_block = True
            else:
                current_node_id = None
            continue

        # 节点块内的 shape 定义
        if in_node_block and current_node_id:
            shape_match = re.match(r'\s*shape:\s*(\w+)', line)
            if shape_match:
                shape = shape_match.group(1).lower()
                if shape in ('diamond',):
                    node_types[current_node_id] = 'decision'
                elif shape in ('circle',):
                    node_types[current_node_id] = 'begin'
                else:
                    node_types[current_node_id] = 'task'

            if '}' in line:
                in_node_block = False
                current_node_id = None
            continue

        # 边定义: a -> b 或 a -> b: label
        edge_match = re.match(
            r'^(\w+)\s*->\s*(\w+)(?:\s*:\s*(.+))?\s*$', line
        )
        if edge_match:
            from_id = edge_match.group(1)
            to_id = edge_match.group(2)
            label = edge_match.group(3) or ""

            for nid in (from_id, to_id):
                if nid not in node_labels:
                    node_labels[nid] = nid

            edges.append(FlowEdge(from_id=from_id, to_id=to_id, label=label.strip()))
            continue

    # 构建节点列表
    for nid, label in node_labels.items():
        ntype = node_types.get(nid, "task")
        nodes.append(FlowNode(
            id=nid,
            type=ntype,
            label=label,
            description="",
        ))
        node_map[nid] = nodes[-1]

    if not nodes:
        raise ValueError("D2 解析失败：未找到任何节点定义")

    start_id, end_id = _detect_start_end(nodes)

    if not start_id and nodes:
        start_id = nodes[0].id
    if not end_id and nodes:
        end_id = nodes[-1].id

    return Flow(
        name="",
        nodes=nodes,
        edges=edges,
        start_id=start_id,
        end_id=end_id,
    )


# ── 内部辅助函数 ──────────────────────────────────────────────

def _parse_mermaid_node(line: str) -> FlowNode | None:
    """解析单行 Mermaid 节点定义

    支持格式：
    - A[Label]        → task 节点
    - B{Label}        → decision 节点
    - C((Label))      → begin/end 节点
    - D([Label])      → begin/end 节点（体育场形）

    Returns:
        解析成功返回 FlowNode，否则返回 None
    """
    line = line.strip()
    if not line:
        return None

    # 决策节点: B{Label} 或 B{Label}
    match = re.match(r'^(\w+)\{(.+?)\}\s*$', line)
    if match:
        return FlowNode(
            id=match.group(1),
            type="decision",
            label=match.group(2).strip(),
        )

    # 圆角/圆形节点: C((Label)) 或 D([Label])
    match = re.match(r'^(\w+)\(\((.+?)\)\)\s*$', line)
    if match:
        label = match.group(2).strip()
        ntype = "end" if _is_end_label(label) else "begin"
        return FlowNode(
            id=match.group(1),
            type=ntype,
            label=label,
        )

    match = re.match(r'^(\w+)\(\[(.+?)\]\)\s*$', line)
    if match:
        return FlowNode(
            id=match.group(1),
            type="begin",
            label=match.group(2).strip(),
        )

    # 矩形节点: A[Label]
    match = re.match(r'^(\w+)\[(.+?)\]\s*$', line)
    if match:
        return FlowNode(
            id=match.group(1),
            type="task",
            label=match.group(2).strip(),
        )

    return None


def _parse_mermaid_edge(line: str) -> FlowEdge | None:
    """解析单行 Mermaid 边定义

    支持格式：
    - A --> B
    - A -->|condition| B

    Returns:
        解析成功返回 FlowEdge，否则返回 None
    """
    line = line.strip()
    if not line:
        return None

    # 带标签的边: A -->|label| B
    match = re.match(r'^(\w+)\s*-+>\s*\|(.+?)\|\s*(\w+)\s*$', line)
    if match:
        return FlowEdge(
            from_id=match.group(1),
            to_id=match.group(3),
            label=match.group(2).strip(),
        )

    # 普通边: A --> B
    match = re.match(r'^(\w+)\s*-+>\s*(\w+)\s*$', line)
    if match:
        return FlowEdge(
            from_id=match.group(1),
            to_id=match.group(2),
        )

    return None


def _detect_start_end(nodes: list[FlowNode]) -> tuple[str, str]:
    """自动检测流程的起始和结束节点

    检测策略：
    1. 查找 type 为 "begin"/"end" 的节点
    2. 查找标签包含 "开始"/"结束"/"start"/"end"/"begin" 的节点
    3. 返回空字符串表示未检测到

    Returns:
        (start_id, end_id) 元组
    """
    start_id = ""
    end_id = ""

    for node in nodes:
        if node.type == "begin" and not start_id:
            start_id = node.id
        if node.type == "end" and not end_id:
            end_id = node.id

    # 如果 type 没标记，通过标签推断
    if not start_id:
        for node in nodes:
            if _is_start_label(node.label):
                start_id = node.id
                break

    if not end_id:
        for node in nodes:
            if _is_end_label(node.label):
                end_id = node.id
                break

    return start_id, end_id


def _is_start_label(label: str) -> bool:
    """检查标签是否为起始标记"""
    lower = label.strip().lower()
    return lower in ("开始", "start", "begin", "起始")


def _is_end_label(label: str) -> bool:
    """检查标签是否为结束标记"""
    lower = label.strip().lower()
    return lower in ("结束", "end", "finish", "完成")
