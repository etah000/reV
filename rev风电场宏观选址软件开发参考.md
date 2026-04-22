# 输出"风电场宏观选址软件参考手册"

## 1. 文档目标

本文面向软件开发人员，目标不是介绍 reV 的学术背景，而是说明如何把 reV 作为计算引擎，开发一个可运行、可扩展、可维护的风电场宏观选址软件系统。

本文重点回答以下问题：

1. 软件系统应该把 reV 放在什么位置。
2. 最小可用系统需要哪些输入、模块和输出。
3. 应优先使用 reV 的哪些 CLI 和 Python API。
4. 如何把结果封装成后端服务、任务系统和可视化能力。

## 2. 先定义系统边界

开发风电场宏观选址系统时，不建议重写一个 reV。正确做法是把 reV 作为专业计算内核，而业务系统负责流程管理、数据治理和结果服务。

建议按如下边界划分职责：

- reV 负责风资源发电模拟、供给曲线聚合、输电成本叠加和代表性曲线提取。
- 业务系统负责用户输入、参数管理、配置生成、任务调度、日志追踪、结果入库和前端展示。

对风电宏观选址，reV 的标准计算链路是：

1. `generation`
2. `collect`
3. `multi-year`
4. `supply-curve-aggregation`
5. `supply-curve`
6. `rep-profiles`
7. `qa-qc`

对应代码入口可参考：

- [reV/cli.py](reV/cli.py)
- [reV/generation/generation.py](reV/generation/generation.py)
- [reV/utilities/__init__.py](reV/utilities/__init__.py)

## 3. 推荐的软件系统架构

建议按五层来设计。

### 3.1 展示层

负责地图选区、参数填写、场景对比、任务状态展示和结果导出。展示层不直接调用 reV，而是调用你们自己的后端 API。

### 3.2 业务服务层

负责把用户输入转成一个“选址任务”。典型职责包括：

- 创建任务。
- 保存场景参数。
- 选择风机模板。
- 选择分析年份。
- 选择排除规则。
- 触发任务执行。
- 查询任务状态。
- 读取结果摘要。

### 3.3 配置生成层

这是系统最关键的一层，用于把数据库中的业务参数转换成 reV 所需的输入文件和 JSON 配置文件，包括：

- `project_points.csv`
- `config_gen.json`
- `config_collect.json`
- `config_multi-year.json`
- `config_aggregation.json`
- `config_supply-curve.json`
- `config_rep-profiles.json`
- `config_qa-qc.json`
- `config_pipeline.json`

### 3.4 执行层

执行层负责任务落地运行，建议优先使用 reV CLI，而不是把所有模块都直接嵌进 Web 服务进程中。

核心命令包括：

- `reV pipeline`
- `reV project-points`
- `reV generation`
- `reV collect`
- `reV multi-year`
- `reV supply-curve-aggregation`
- `reV supply-curve`
- `reV rep-profiles`
- `reV qa-qc`
- `reV status`
- `reV reset-status`

这些命令在代码和官方文档中的命名保持一致，参考：

- [reV/cli.py](reV/cli.py)
- [reV/utilities/__init__.py](reV/utilities/__init__.py)

### 3.5 结果服务层

负责读取输出文件、提取关键字段、入库并提供给前端或报表系统。典型职责包括：

- 把供给曲线结果转换成地图图层。
- 把关键指标转换成表格结果。
- 提供排序、筛选、导出和统计接口。
- 提供代表性出力曲线下载接口。

## 4. 运行环境设计

### 4.1 本地开发环境

根据 [pyproject.toml](pyproject.toml) 和 [README.rst](README.rst)，reV 的 Python 版本要求是 3.11 及以上。推荐本地环境如下：

```bash
conda create --name rev python=3.11
conda activate rev
pip install NLR-reV
```

如果需要 HSDS 支持：

```bash
pip install NLR-reV[hsds]
```

本地环境适合：

- 开发配置生成器。
- 调试 `project_points` 生成逻辑。
- 做小区域样本计算。
- 验证单模块输出结构。

### 4.2 大规模运行环境

对于区域级、全国级、多年份和多方案分析，应按 HPC 或云端并行任务来设计。

示例配置显示的大规模执行特征包括：

- `nodes`
- `memory`
- `sites_per_worker`
- `walltime`

可参考以下文件：

- [examples/batched_execution/config_gen.json](examples/batched_execution/config_gen.json)
- [examples/full_pipeline_execution/config_aggregation.json](examples/full_pipeline_execution/config_aggregation.json)
- [examples/full_pipeline_execution/config_supply-curve.json](examples/full_pipeline_execution/config_supply-curve.json)
- [examples/full_pipeline_execution/config_rep-profiles.json](examples/full_pipeline_execution/config_rep-profiles.json)
- [examples/aws_pcluster/README.md](examples/aws_pcluster/README.md)

工程上应这样理解：

- 本地环境用于开发和小范围验证。
- 集群环境用于正式批量计算。
- 业务系统应天然支持两套执行器，而不是只绑定一种部署方式。

## 5. 输入数据契约设计

在实现软件系统前，必须先把输入数据契约设计清楚。否则前端、后端和 reV 执行层会长期错位。

### 5.1 风资源数据

风电分析依赖 HDF5 资源文件，示例中常用的是 WTK 数据：

```json
{
  "resource_file": "/datasets/WIND/conus/v1.0.0/wtk_conus_{}.h5",
  "technology": "windpower"
}
```

建议在系统中单独维护资源数据集实体，而不是把路径硬编码在配置里。最少应维护以下字段：

- `dataset_id`
- `name`
- `technology`
- `path_pattern`
- `analysis_years`
- `extent`
- `resolution`
- `status`

### 5.2 项目点 `project_points`

这是系统和 reV 的第一个硬接口。示例见 [examples/batched_execution/project_points/project_points.csv](examples/batched_execution/project_points/project_points.csv)。

最小格式如下：

```csv
gid,config
0,turbine
1,turbine
2,turbine
```

含义：

- `gid` 是资源点编号。
- `config` 是该点绑定的 SAM 配置名。

建议系统内部不要只保存这个最小结构，而是维护更完整的候选点表，例如：

- `candidate_id`
- `gid`
- `lat`
- `lon`
- `region_code`
- `terrain_class`
- `sam_config_name`
- `scenario_id`

然后由配置生成器导出 reV 所需的最小 CSV。

### 5.3 SAM 风机配置

示例见 [examples/batched_execution/sam_configs/turbine.json](examples/batched_execution/sam_configs/turbine.json)。

风电配置通常包括：

- `system_capacity`
- `wind_turbine_hub_ht`
- `wind_farm_losses_percent`
- `wind_farm_wake_model`
- `wind_turbine_powercurve_powerout`
- `wind_farm_xCoordinates`
- `wind_farm_yCoordinates`

建议系统实现“风机模板库”，不要让用户直接编辑原始 JSON。更合理的方式是：

- 前端编辑结构化表单。
- 后端根据模板和参数渲染 SAM JSON。
- 配置渲染结果在任务目录中固化留档。

### 5.4 排除层与约束条件

排除层是宏观选址系统的核心输入之一。示例见 [examples/full_pipeline_execution/config_aggregation.json](examples/full_pipeline_execution/config_aggregation.json)。

典型结构：

```json
{
  "excl_fpath": "./rev_conus_exclusions.h5",
  "excl_dict": {
    "srtm_slope": {
      "inclusion_range": [null, 5],
      "weight": 1.0
    }
  }
}
```

建议把排除规则建模为系统对象，而不是让用户直接拼 JSON。比如：

- 图层名
- 规则类型
- 最小值
- 最大值
- 是否加权
- 权重值
- 是否启用

最后由配置生成器把这些结构化规则渲染成 `excl_dict`。

### 5.5 输电成本表

示例见 [examples/full_pipeline_execution/config_supply-curve.json](examples/full_pipeline_execution/config_supply-curve.json)。

业务系统不应只把输电成本表视为一个上传文件，而应管理：

- 输电网络版本
- 接入点版本
- 成本假设版本
- 区域适用范围
- 已生成的 `trans_table`

## 6. 优先使用哪些 reV 接口

### 6.1 优先使用 CLI 做标准流程

对正式软件系统，优先建议使用 CLI 执行完整计算链路，而不是把每一个模块都直接嵌入 Web 请求线程中。

理由：

- 配置和执行天然分离。
- 更适合异步任务系统。
- 更适合 HPC 和批量执行。
- 更容易复现和审计。
- 更容易利用 `pipeline`、`status` 和失败重跑机制。

标准运行方式参考 [examples/full_pipeline_execution/README.rst](examples/full_pipeline_execution/README.rst)：

```bash
reV pipeline -c ./config_pipeline.json
```

需要持续监控时：

```bash
reV pipeline -c ./config_pipeline.json --monitor
```

### 6.2 使用 Python API 做原型和辅助逻辑

Python API 更适合两类工作：

1. 原型验证和本地小范围试算。
2. 系统中的辅助逻辑，例如候选点生成、输入预校验、即时预览。

常用入口包括：

- `Gen`，见 [reV/generation/generation.py](reV/generation/generation.py)
- 顶层导出，见 [reV/__init__.py](reV/__init__.py)
- `ProjectPoints` 的 CLI 映射，见 [reV/config/cli_project_points.py](reV/config/cli_project_points.py)

### 6.3 `project-points` 命令适合系统接入

reV 提供了标准的项目点生成入口：

- `reV project-points from-lat-lons`
- `reV project-points from-regions`

这意味着系统可以直接把两类用户输入映射到 reV：

1. 地图框选或上传的经纬度点。
2. 行政区或区域边界。

## 7. 最小可用系统实现路径

建议分三阶段推进。

### 7.1 第一阶段：离线 MVP

目标不是做完整平台，而是先证明端到端链路可跑通。

MVP 至少应包含：

- 一个任务创建接口。
- 一个配置生成器。
- 一个执行器，能调用 `reV pipeline`。
- 一个结果解析器。
- 一个简单地图页或结果表格页。

输入最少只支持：

- 资源数据集选择
- 分析年份
- 风机模板
- 基础排除规则
- 输电成本版本

输出最少展示：

- `capacity_ac_mw`
- `capacity_factor_ac`
- `lcoe_site_usd_per_mwh`
- `lcoe_all_in_usd_per_mwh`
- `area_developable_sq_km`

这些输出字段在 [reV/utilities/__init__.py](reV/utilities/__init__.py) 中有定义。

### 7.2 第二阶段：区域级系统

在 MVP 基础上增加：

- 多场景比较
- 多年统计
- 异步任务队列
- 结果入库
- QA/QC 页面
- 代表性曲线导出

### 7.3 第三阶段：生产化系统

再进一步增加：

- HPC 或云端执行器
- 任务优先级
- 失败自动重试
- 配置版本化
- 数据血缘追踪
- 审计日志
- 大结果集分页与地图瓦片化

## 8. 配置生成器设计

配置生成器是整套系统中最值得认真实现的模块。

建议为每个任务生成独立运行目录，例如：

```text
jobs/
  job_20260422_001/
    inputs/
      project_points.csv
      sam_configs/
        turbine.json
    configs/
      config_gen.json
      config_collect.json
      config_multi-year.json
      config_aggregation.json
      config_supply-curve.json
      config_rep-profiles.json
      config_qa-qc.json
      config_pipeline.json
    outputs/
    logs/
```

### 8.1 `config_gen.json`

风电生成配置可参考 [examples/batched_execution/config_gen.json](examples/batched_execution/config_gen.json)：

```json
{
  "analysis_years": [2010, 2011],
  "log_directory": "./logs/",
  "project_points": "./inputs/project_points.csv",
  "resource_file": "/datasets/WIND/conus/v1.0.0/wtk_conus_{}.h5",
  "sam_files": {
    "turbine": "./inputs/sam_configs/turbine.json"
  },
  "technology": "windpower",
  "output_request": ["cf_mean", "cf_profile", "lcoe_fcr", "ws_mean"]
}
```

### 8.2 `config_aggregation.json`

聚合配置可参考 [examples/full_pipeline_execution/config_aggregation.json](examples/full_pipeline_execution/config_aggregation.json)。

关键点包括：

- `excl_fpath`
- `excl_dict`
- `gen_fpath: "PIPELINE"`
- `lcoe_dset`
- `cf_dset`
- `power_density`
- `resolution`

`PIPELINE` 的解析逻辑可参考 [reV/utilities/cli_functions.py](reV/utilities/cli_functions.py)。

### 8.3 `config_supply-curve.json`

输电和综合成本配置可参考 [examples/full_pipeline_execution/config_supply-curve.json](examples/full_pipeline_execution/config_supply-curve.json)。

关键点包括：

- `sc_points: "PIPELINE"`
- `trans_table`
- `transmission_costs`
- `fixed_charge_rate`

### 8.4 `config_rep-profiles.json`

代表性曲线配置可参考 [examples/full_pipeline_execution/config_rep-profiles.json](examples/full_pipeline_execution/config_rep-profiles.json)。

关键参数包括：

- `n_profiles`
- `rep_method`
- `reg_cols`
- `gen_fpath: "PIPELINE"`
- `rev_summary: "PIPELINE"`

### 8.5 `config_pipeline.json`

标准流程顺序可直接参考 [examples/full_pipeline_execution/config_pipeline.json](examples/full_pipeline_execution/config_pipeline.json)：

```json
{
  "logging": {
    "log_file": null,
    "log_level": "INFO"
  },
  "pipeline": [
    {"generation": "./configs/config_gen.json"},
    {"collect": "./configs/config_collect.json"},
    {"multi-year": "./configs/config_multi-year.json"},
    {"supply-curve-aggregation": "./configs/config_aggregation.json"},
    {"supply-curve": "./configs/config_supply-curve.json"},
    {"rep-profiles": "./configs/config_rep-profiles.json"},
    {"qa-qc": "./configs/config_qa-qc.json"}
  ]
}
```

## 9. 后端如何封装 reV

### 9.1 不要同步执行长任务

不要让 Web 请求直接执行 reV。建议采用异步任务模式：

1. API 接收任务参数。
2. 后端保存任务。
3. 生成输入文件和配置文件。
4. 投递到任务队列。
5. Worker 调用 reV CLI 执行。
6. 回填状态、日志和结果摘要。

### 9.2 建议的后端服务拆分

建议拆分为以下服务：

- `dataset_service`
- `scenario_service`
- `rev_config_service`
- `rev_runner_service`
- `result_parser_service`
- `report_service`

### 9.3 建议的 API

最少应提供：

- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/logs`
- `GET /jobs/{job_id}/summary`
- `GET /jobs/{job_id}/supply-curve`
- `GET /jobs/{job_id}/profiles`

## 10. Python API 的典型原型用法

如果不想一开始就跑完整 pipeline，可以先用 Python API 做最小原型。参考 [examples/running_locally/README.rst](examples/running_locally/README.rst) 中的风电示例：

```python
import numpy as np
from reV.config.project_points import ProjectPoints
from reV.generation.generation import Gen

lat_lons = np.array([
    [41.25, -71.66],
    [41.05, -71.74],
])

res_file = "/path/to/wtk_2012.h5"
sam_file = "/path/to/windpower.json"

pp = ProjectPoints.lat_lon_coords(lat_lons, res_file, sam_file)
gen = Gen(
    "windpower",
    pp,
    sam_file,
    res_file,
    output_request=("cf_mean", "cf_profile")
)
gen.run(max_workers=1)
print(gen.out["cf_mean"])
```

这个模式适合：

- 候选点试算
- 参数联调
- 前端即时预览
- 单点调试

但不适合作为大规模生产执行方案。

## 11. 输出解析与结果入库

不要把 reV 的输出简单理解成“生成文件后下载即可”，系统应该把它转换成结构化结果服务。

建议把输出分为三类。

### 11.1 任务级摘要

建议入库字段包括：

- 任务 ID
- 场景名称
- 年份范围
- 区域范围
- 总可开发容量
- 最低综合 LCOE
- 平均容量因子
- 任务状态
- 执行耗时

### 11.2 供给曲线点结果

建议至少解析以下字段，名称可参考 [reV/utilities/__init__.py](reV/utilities/__init__.py)：

- `sc_gid`
- `latitude`
- `longitude`
- `capacity_ac_mw`
- `capacity_factor_ac`
- `lcoe_site_usd_per_mwh`
- `lcot_usd_per_mwh`
- `lcoe_all_in_usd_per_mwh`
- `area_developable_sq_km`
- `annual_energy_site_mwh`
- `latitude_poi`
- `longitude_poi`

### 11.3 时序结果

代表性曲线通常数据量较大，不建议全部塞进主业务库。更合理的方式是：

- 摘要值入业务库。
- 原始曲线存对象存储或时序库。
- 前端按需拉取。

## 12. QA 与错误控制

要把系统做成产品，必须把 QA 做成内建能力。

### 12.1 输入校验

在执行前，至少校验：

- 资源文件路径是否存在。
- 分析年份是否和资源数据匹配。
- `project_points` 是否为空。
- `gid` 是否落在资源覆盖范围内。
- SAM 配置是否完整。
- 排除层图层名是否存在。
- 输电成本表字段是否完整。

### 12.2 执行校验

建议结合 pipeline 状态和日志检查：

- 每一步是否产生输出。
- pipeline 状态是否成功。
- 失败步骤的 stdout 和 stderr。

### 12.3 结果校验

建议至少做以下校验：

- 容量因子范围校验。
- LCOE 合理性校验。
- 可开发面积非负校验。
- 供给曲线点数量和空间范围校验。
- 重点区域 spot check。

`qa-qc` 的配置结构可参考 [examples/full_pipeline_execution/config_qa-qc.json](examples/full_pipeline_execution/config_qa-qc.json)。

## 13. 常见开发错误

1. 把 reV 当成在线实时计算引擎，直接绑定到同步 HTTP 请求。
2. 把业务参数手写进 JSON，而不是做配置生成器。
3. 让多个任务共用同一个输出目录。
4. 不对 `project_points`、风机模板和成本假设做版本化。
5. 直接把示例中的测试参数拿来做真实工程参数。
6. 只输出文件，不做结构化结果入库。
7. 先上大规模任务，再补输入校验和小范围验证。

## 14. 推荐开发顺序

建议按以下顺序推进：

1. 跑通本地 `Gen` 小样本试算。
2. 实现 `project_points` 生成逻辑。
3. 实现配置生成器。
4. 用 `reV pipeline` 跑通一条完整离线任务。
5. 实现任务状态表和结果摘要表。
6. 实现供给曲线点结果入库。
7. 接入地图展示。
8. 再做集群化、云化和报表化。

## 15. 参考材料

最值得反复查看的仓库文件包括：

- [README.rst](README.rst)
- [pyproject.toml](pyproject.toml)
- [reV/cli.py](reV/cli.py)
- [reV/__init__.py](reV/__init__.py)
- [reV/config/cli_project_points.py](reV/config/cli_project_points.py)
- [reV/generation/generation.py](reV/generation/generation.py)
- [reV/utilities/cli_functions.py](reV/utilities/cli_functions.py)
- [reV/utilities/__init__.py](reV/utilities/__init__.py)
- [examples/running_locally/README.rst](examples/running_locally/README.rst)
- [examples/full_pipeline_execution/README.rst](examples/full_pipeline_execution/README.rst)
- [examples/full_pipeline_execution/config_pipeline.json](examples/full_pipeline_execution/config_pipeline.json)
- [examples/batched_execution/config_gen.json](examples/batched_execution/config_gen.json)
- [examples/batched_execution/project_points/project_points.csv](examples/batched_execution/project_points/project_points.csv)
- [examples/batched_execution/sam_configs/turbine.json](examples/batched_execution/sam_configs/turbine.json)
- [examples/offshore_wind/README.rst](examples/offshore_wind/README.rst)
- [examples/aws_pcluster/README.md](examples/aws_pcluster/README.md)

官方和外部资料：

- reV 官方文档：<https://natlabrockies.github.io/reV/>
- reV CLI 文档：<https://natlabrockies.github.io/reV/_cli/cli.html>
- GitHub 仓库：<https://github.com/NatLabRockies/reV>
- 技术报告 73067：<https://docs.nrel.gov/docs/fy19osti/73067.pdf>

## 16. 结论

开发风电场宏观选址软件系统时，reV 最适合被定位为“专业计算引擎”，而不是完整业务平台。系统建设的核心难点不在于调用一个命令，而在于把输入数据、配置生成、任务执行、结果解析和前端服务组织成一条稳定、可审计、可扩展的工程链路。

如果按本文建议的方式实现，开发团队可以先完成离线 MVP，再逐步扩展到区域级和生产级部署，而不需要一开始就承担过高的系统复杂度。