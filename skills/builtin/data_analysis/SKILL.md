---
name: data-analysis
description: 对上传的数据文件进行分析，生成统计摘要和可视化建议
type: standard
tools: [read_file, write_file, run_command]
when_to_use: 当用户上传 Excel/CSV 数据文件并需要分析时使用
agent: analyzer
---

# 数据分析技能

## 任务
对结构化数据文件进行全面分析。

## 分析步骤
1. 数据概览：行数、列数、数据类型
2. 描述性统计：均值、中位数、标准差
3. 缺失值分析：缺失率和分布
4. 相关性分析：数值列间的相关性
5. 可视化建议：推荐合适的图表类型
