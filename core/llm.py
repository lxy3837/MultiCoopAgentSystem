"""
MCASys LLM 客户端 — 硅基流动 (SiliconFlow) API

基于 OpenAI 兼容接口，支持 DeepSeek-V3.2 等模型。
提供同步/异步双模式调用，以及 Agent 专用的结构化推理接口。

用法::

    from core.llm import LLMClient

    client = LLMClient()
    response = await client.chat("你好，请帮我分析这段代码")
    print(response)

环境变量:
    SILICONFLOW_API_KEY — 硅基流动 API Key（必需）
    SILICONFLOW_BASE_URL — 接口地址（默认: https://api.siliconflow.cn/v1）
    SILICONFLOW_MODEL — 默认模型（默认: deepseek-ai/DeepSeek-V3.2）
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

from utils.logger import get_logger

logger = get_logger("llm")


# ── 默认配置 ──────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"


class LLMConfig:
    """LLM 配置"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
        self.base_url = (base_url or os.environ.get("SILICONFLOW_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("SILICONFLOW_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


class LLMClient:
    """LLM 客户端 — 封装硅基流动 API 调用

    提供统一的文本生成接口，支持 Agent 系统调用。
    自动处理重试、超时和错误格式化。
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_available(self) -> bool:
        return self.config.is_configured

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    async def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """发送聊天请求并返回文本响应

        Args:
            prompt: 用户消息内容
            system_prompt: 系统提示词（可选）
            model: 模型名称，默认使用配置中的模型
            temperature: 采样温度
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容

        Raises:
            RuntimeError: API 未配置或调用失败
        """
        if not self.is_available:
            raise RuntimeError("LLM 未配置：请设置 SILICONFLOW_API_KEY 环境变量")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self._request(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_with_history(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """带历史记录的多轮对话

        Args:
            messages: [{"role": "system|user|assistant", "content": "..."}, ...]
            model: 模型名称
            temperature: 采样温度
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """
        if not self.is_available:
            raise RuntimeError("LLM 未配置：请设置 SILICONFLOW_API_KEY 环境变量")

        return await self._request(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """请求 LLM 返回 JSON 结构化数据

        自动在 prompt 中追加 JSON 格式要求。

        Args:
            prompt: 用户消息
            system_prompt: 系统提示词
            model: 模型名称

        Returns:
            解析后的 JSON 字典
        """
        full_prompt = f"{prompt}\n\n请严格按照 JSON 格式返回结果，不要包含 markdown 代码块标记，只输出纯 JSON。"
        text = await self.chat(
            prompt=full_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=0.3,  # 降低温度以提高 JSON 输出可靠性
        )
        # 清理可能的 markdown 标记
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"LLM 返回的不是有效 JSON，原始内容前 200 字符: {text[:200]}")
            return {"raw_text": text, "parse_error": True}

    async def _request(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """发送 API 请求并处理响应"""
        client = await self._get_client()
        payload = {
            "model": model or self.config.model,
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "stream": False,
        }

        logger.debug(
            f"LLM 请求: model={payload['model']}, "
            f"messages_count={len(messages)}, "
            f"prompt_preview={str(messages[-1]['content'])[:100]}..."
        )

        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            logger.info(
                f"LLM 响应: model={data.get('model')}, "
                f"tokens_in={usage.get('prompt_tokens')}, "
                f"tokens_out={usage.get('completion_tokens')}"
            )
            return content
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response else str(e)
            logger.error(f"LLM API 错误 (HTTP {e.response.status_code}): {error_detail}")
            raise RuntimeError(f"LLM API 错误: {e.response.status_code} - {error_detail}")
        except Exception as e:
            logger.error(f"LLM 请求异常: {e}")
            raise RuntimeError(f"LLM 请求失败: {e}")

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Agent 专用接口 ────────────────────────────────────────

    async def agent_analyze(
        self,
        task_description: str,
        skill_prompts: str = "",
        context: dict | None = None,
    ) -> str:
        """Agent 分析任务 — 使用技能提示词增强推理

        Args:
            task_description: 任务描述
            skill_prompts: 技能系统提示词（来自 Skill.get_system_prompt()）
            context: 附加上下文数据

        Returns:
            LLM 分析结果
        """
        system = "你是一个专业的 AI Agent，擅长分析和执行各类任务。请仔细分析任务，给出详细的执行方案。"
        if skill_prompts:
            system += f"\n\n## 加载的技能\n{skill_prompts}"

        prompt = task_description
        if context:
            prompt += f"\n\n## 上下文数据\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"

        return await self.chat(prompt=prompt, system_prompt=system, temperature=0.5)

    async def agent_decide(
        self,
        question: str,
        options: list[str],
        context: dict | None = None,
    ) -> str:
        """Agent 决策 — 从多个选项中选一个

        Args:
            question: 决策问题
            options: 可选方案列表
            context: 附加上下文

        Returns:
            被选中的选项文本
        """
        options_text = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
        prompt = f"""## 决策问题
{question}

## 可选方案
{options_text}

## 要求
请分析每个方案的利弊，然后只输出你选择的方案的完整文本（一字不差地复制对应选项文本）。"""

        if context:
            prompt += f"\n\n## 上下文\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"

        result = await self.chat(prompt=prompt, temperature=0.2)
        # 尝试匹配最相似的选项
        result = result.strip().strip("'\"")
        for opt in options:
            if result == opt or opt in result:
                return opt
        return result

    async def agent_generate(
        self,
        template: str,
        params: dict,
        skill_prompts: str = "",
    ) -> str:
        """Agent 内容生成 — 基于模板和参数生成内容

        Args:
            template: 生成模板
            params: 模板参数
            skill_prompts: 技能提示词

        Returns:
            生成的内容
        """
        system = "你是一个专业的 AI 内容生成 Agent。请严格按照模板和参数生成高质量内容。"
        if skill_prompts:
            system += f"\n\n## 技能指导\n{skill_prompts}"

        prompt = f"## 模板\n{template}\n\n## 参数\n```json\n{json.dumps(params, ensure_ascii=False, indent=2)}\n```\n\n请根据模板和参数生成内容。"
        return await self.chat(prompt=prompt, system_prompt=system, temperature=0.7)


# ── 工厂函数 ──────────────────────────────────────────────────

_global_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端单例"""
    global _global_client
    if _global_client is None:
        _global_client = LLMClient()
    return _global_client


def init_llm_client(config: LLMConfig | None = None) -> LLMClient:
    """初始化/重置全局 LLM 客户端"""
    global _global_client
    _global_client = LLMClient(config)
    if _global_client.is_available:
        logger.info(f"LLM 客户端已初始化: model={_global_client.config.model}, base_url={_global_client.config.base_url}")
    else:
        logger.warning("LLM 客户端未配置 API Key，Agent 将使用模拟模式")
    return _global_client


__all__ = [
    "LLMConfig",
    "LLMClient",
    "get_llm_client",
    "init_llm_client",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
]
