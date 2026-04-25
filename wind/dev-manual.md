# reV 风电场宏观选址开发手册

> 目标受众：软件工程师。本手册聚焦于 reV 风电场宏观选址（Wind Farm Macro Siting）的完整流程，覆盖每个步骤的输入输出、可调整顺序、可选性分析、可运行示例以及数据格式支持。

---

## 目录

1. [概述](#1-概述)
2. [完整流程图](#2-完整流程图)
3. [流程各步骤详解](#3-流程各步骤详解)

- 3.1 [Generation 阶段（资源到发电时序）](#31-generation-阶段资源到发电时序)
  - 3.1.1 [Generation（发电量模拟）](#311-generation发电量模拟)
  - 3.1.2 [Collect（分片合并）](#312-collect分片合并)
  - 3.1.3 [Multi-Year（多年均值）](#313-multi-year多年均值)
- 3.2 [Exclusion 阶段（空间约束与可开发面积聚合）](#32-exclusion-阶段空间约束与可开发面积聚合)
- 3.3 [Supply Curve 阶段（成本叠加与排序）](#33-supply-curve-阶段成本叠加与排序)
  - 3.3.1 [Supply-Curve（供应曲线输电定价）](#331-supply-curve供应曲线输电定价)
  - 3.3.2 [Rep-Profiles（代表性时间序列）](#332-rep-profiles代表性时间序列)
  - 3.3.3 [QA-QC（质量检查）](#333-qa-qc质量检查)

4. [阶段顺序与可选性矩阵](#4-阶段顺序与可选性矩阵)
5. [Bespoke 风场布局优化（替代路径）](#5-bespoke-风场布局优化替代路径)
6. [可运行示例](#6-可运行示例)

- 6.1 [本地单年风电 Pipeline（TESTDATADIR 数据）](#61-本地单年风电-pipeline)
- 6.2 [Bespoke 风场布局优化](#62-bespoke-风场布局优化)
- 6.3 [官方示例核验与完整操作流程](#63-官方示例核验与完整操作流程)

7. [数据获取与合成数据生成](#7-数据获取与合成数据生成)
8. [输入数据格式支持](#8-输入数据格式支持)
   - 8.1 [资源文件 HDF5 规范（rex）](#81-资源文件-hdf5-规范rex)
   - 8.2 [排除层文件 HDF5 规范](#82-排除层文件-hdf5-规范)
   - 8.3 [添加自定义数据接口](#83-添加自定义数据接口)
9. [关键 API 参考索引](#9-关键-api-参考索引)

---

## 1. 概述

reV（Renewable Energy Potential Model）是 NREL 开发的地理空间技术经济分析工具，用于评估可再生能源（风电、光伏、地热、波浪等）的开发潜力。

**风电场宏观选址的核心目标**：

1. 在每个候选站点运行 SAM（System Advisor Model）物理模拟，获取风能捕获特性（`cf_mean`、`cf_profile` 等）
2. 与地理排除图层（保护区、坡度、电网缓冲区等）叠加，识别可开发区域
3. 将高分辨率（~90m）结果聚合为供应曲线分辨率（如 64×64 = 4km² 格网）
4. 叠加输电成本，生成按 LCOE 排序的供应曲线
5. （可选）提取每个聚合区域的代表性发电时序用于后续电网分析

---

## 2. 完整流程图

```
[Wind Resource Files (WTK .h5)]
         │
         ▼
┌─────────────────────────┐
│   1. Generation          │  → output_dir/*_gen_{year}.h5（或分片 _node*.h5）
│   (SAM WindPower 模拟)   │
└─────────────────────────┘
         │ (上游产生多分片文件时)
         ▼
┌─────────────────────────┐
│   2. Collect             │  → output_dir/*_gen_{year}.h5（合并分片）
│   (分片 HDF5 合并)       │
└─────────────────────────┘
         │ (使用多个年份输入时)
         ▼
┌─────────────────────────┐
│   3. Multi-Year          │  → output_dir/*_multi_year.h5
│   (多年统计平均)         │     (包含 cf_mean-means, cf_mean-stdev 等)
└─────────────────────────┘
         │
         ▼
[Exclusion Layers .h5]  ──┐
[TechMap dataset]         │
                          ▼
┌─────────────────────────┐
│   4. SC-Aggregation      │  → output_dir/*_sc_agg.csv
│   (排除+聚合→供应曲线)   │
└─────────────────────────┘
         │
[Transmission Table .csv] │
                          ▼
┌─────────────────────────┐
│   5. Supply-Curve        │  → output_dir/*_sc.csv
│   (叠加输电成本)         │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│   6. Rep-Profiles        │  → output_dir/*_rep_profiles.h5
│   (代表性时间序列)        │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│   7. QA-QC（可选）       │  → 图表/报告
└─────────────────────────┘
```

---

## 3. 流程各步骤详解

本节按 NREL 技术报告（`73067`）与 reV 官方文档的执行逻辑，将风电宏观选址流程划分为 3 个主阶段：

1. Generation：资源驱动的发电模拟（含分片合并与多年统计）
2. Exclusion：空间约束叠加与可开发面积/潜力聚合
3. Supply Curve：输电成本叠加、经济性排序与结果抽样

### 3.1 Generation 阶段（资源到发电时序）

#### 3.1.1 Generation（发电量模拟）

**目的**：对 `project_points` 中每个站点，调用 SAM `WindPower` 模块做逐小时物理模拟。

**核心类**：`reV.generation.generation.Gen`

**必须输入**：

| 参数 | 说明 |
| --- | --- |
| `technology` | `"windpower"` |
| `project_points` | 待评估资源站点集合，可为单个 `gid`、`gid` 列表/切片、CSV、DataFrame、dict 或 `ProjectPoints` 对象 |
| `sam_files` | 单个 SAM 配置文件，或配置文件字典；当存在多个 SAM 配置时，由 `project_points.config` 指定映射关系 |
| `resource_file` | WTK 风资源 HDF5 文件路径，多年时用 `{}` 占位符 |

**`project_points` 是如何确定的**：

官方文档对 Project Points 的定义是：它用于指定“哪些资源站点（`gids`）要送入 PySAM 计算，以及这些站点使用哪套 SAM 配置”。从当前仓库源码和官方示例看，`project_points` 常见有 4 种确定方式：

1. 直接提供 `project_points.csv`：最常见的工程方式。CSV 最少只需要 `gid` 列；如果 `sam_files` 只有一个配置，`config` 列可以省略。
2. 直接提供 `gid` 列表或切片：适合开发测试、小规模验证。
3. 通过经纬度生成：使用 `ProjectPoints.lat_lon_coords()`，把候选点坐标映射到最近的资源格点 `gid`。
4. 通过区域筛选生成：使用 `ProjectPoints.regions()`，按资源文件 `meta` 中的州、县等区域字段提取 `gid`。

在实际风电宏观选址中，`project_points` 通常不是人工拍脑袋指定，而是按以下流程得到：先确定研究区边界或候选点坐标，再基于资源文件 `meta` 提取或映射对应的资源 `gid`，最后生成 `project_points.csv`，并可附加 `config`、`curtailment` 或站点级 SAM 参数列。要注意的是，`project_points` 只是 **Generation 阶段的资源采样点集合**，它不等同于可建设区域；真正的用地约束和可开发面积筛选发生在后面的 Exclusion 阶段。

**可选输出请求**（`output_request`）：

- `cf_mean` — 容量系数均值（必须，用于后续聚合）
- `cf_profile` — 8760 小时容量系数序列（rep-profiles 必须）
- `lcoe_fcr` — 平准化电力成本
- `wind_direction` — 风向（需 SAM 配置支持）
- `ws_mean` — 风速均值

**SAM 配置文件关键字段**（`i_windpower.json`）：

```json
{
  "wind_turbine_hub_ht": 80,
  "wind_turbine_rotor_diameter": 77,
  "wind_turbine_powercurve_windspeeds": [...],
  "wind_turbine_powercurve_powerout": [...],
  "wind_farm_wake_model": 0,
  "wind_farm_losses_percent": 0,
  "system_capacity": 48000
}
```

`wind_resource_filename` 字段由 reV 自动注入，**不要在 SAM 配置中设置**。

**配置文件示例**（`config_gen_wind.json`）：

```json
{
  "technology": "windpower",
  "project_points": "./project_points_ri.csv",
  "sam_files": {
    "default": "./sam_windpower.json"
  },
  "resource_file": "./wtk/ri_100_wtk_{}.h5",
  "analysis_years": [2012, 2013],
  "output_request": ["cf_mean", "cf_profile"],
  "log_directory": "./logs/",
  "log_level": "INFO",
  "execution_control": {
    "option": "local",
    "max_workers": 4,
    "sites_per_worker": 25
  }
}
```

**Python API 调用**：

```python
from reV.generation.generation import Gen

# project_points 可以直接是 CSV 路径、整数列表、或 ProjectPoints 对象
gen = Gen(
    technology="windpower",
    project_points="project_points_ri.csv",
    sam_files={"default": "sam_windpower.json"},
    resource_file="wtk/ri_100_wtk_2012.h5",
    output_request=("cf_mean", "cf_profile"),
    sites_per_worker=25,   # __init__ 参数：每个 worker 处理的站点数
)
# max_workers 和 out_fpath 是 run() 的参数，不在 __init__ 中
out_file = gen.run(out_fpath="./wind_gen_2012.h5", max_workers=4)
print(f"输出文件: {out_file}")
print(f"内存结果: {gen.out['cf_mean'][:5]}")   # 同时可访问内存中的结果
```

**CLI 调用**：

```bash
reV generation -c config_gen_wind.json
```

**输出文件结构**（`*_gen_2012.h5`）：

- `meta`：DataFrame，包含站点坐标、国家、州、县等
- `time_index`：UTC DatetimeIndex，长度 8760（或 8784 闰年）
- `cf_mean`：shape `(n_sites,)`，标量浮点数组
- `cf_profile`：shape `(8760, n_sites)`，按 `(time, sites)` 顺序存储

---

#### 3.1.2 Collect（分片合并）

**目的**：将上游并行任务产生的多个 HDF5 分片合并为单个标准输出文件，供后续 `multi-year`、`supply-curve-aggregation` 等步骤读取。

**触发条件**：当上游步骤产生多个分片输出时才需要，最常见于多节点 HPC 运行、批处理分块运行，或 pipeline/batch 执行后存在多个 chunk 文件的情况。如果 Generation 已直接输出单个完整 HDF5，则不需要 Collect。

**执行入口**：当前仓库中的 CLI 入口是 `reV.handlers.cli_collect.main`，实际收集逻辑委托给 `gaps.cli.collect.collect`。

**本质说明**：是的，Collect 的本质就是把不同节点或不同子任务处理得到的子结果重新按 `gid` 和数据集维度合并回一个 HDF5 文件。它本身并不重新计算发电量，只做结果收集与文件整理。

**配置文件示例**（`config_collect.json`）：

```json
{
  "log_directory": "./logs/",
  "execution_control": {
    "option": "local"
  },
  "log_level": "INFO",
  "datasets": ["cf_mean", "cf_profile"],
  "project_points": "PIPELINE",
  "purge_chunks": false,
  "clobber": true,
  "collect_pattern": "PIPELINE"
}
```

`"PIPELINE"` 占位符由 pipeline 自动从上一步状态文件解析。`project_points` 也可以直接传 CSV、`gid` 列表，或者设为 `null` 让工具从输入文件自动推断。需要注意的是，Collect 是否需要，取决于 **上游是否产生了多个分片文件**，而不是取决于 Collect 这一步自身配置里 `nodes` 写成多少；实际工程里，Collect 往往作为一个单独的收集任务运行在 1 个节点上。

---

#### 3.1.3 Multi-Year（多年均值）

**目的**：将多个年份的 Generation 输出合并为单个 multi-year HDF5，并为各年度数据保留年份后缀，同时计算跨年均值（`-means`）和标准差（`-stdev`），以降低年际气候波动对选址结论的影响。

**触发条件**：仅当存在两个及以上年度输出文件，并且希望做跨年统计时才有意义。如果只计算了 1 年发电量，通常不需要运行 `multi-year`。

**核心类**：`reV.handlers.multi_year.MultiYear`

**输出数据集命名约定**：

- `cf_mean-2012`、`cf_mean-2013`：各年份原始结果副本
- `cf_mean-means`：跨年均值（后续 SC-Aggregation 常用）
- `cf_mean-stdev`：跨年标准差
- `cf_profile-2012`、`cf_profile-2013`：各年完整时序（前提是 `cf_profile` 被纳入收集）
- `time_index-2012`、`time_index-2013`：各年份时间轴

**配置文件示例**（`config_multi-year.json`）：

```json
{
  "name": "wind_multi_year",
  "log_directory": "./logs/",
  "execution_control": {
    "option": "local",
    "max_workers": 2
  },
  "log_level": "INFO",
  "groups": {
    "none": {
      "dsets": ["cf_mean"],
      "source_dir": "./",
      "source_prefix": "wind_gen"
    }
  }
}
```

**单年是否需要 Multi-Year**：

不需要。`multi-year` 的价值不在于“把一个年文件换个名字”，而在于把多个独立年份的 Generation 结果汇总后，生成跨年统计量。如果只有 1 年数据，直接将该年 Generation 输出送入 Exclusion / Supply Curve 即可。

**实际应用一般选几年输入**：

reV 官方文档强调模型支持“从单一年份到多个年代（multiple decades）”的资源输入，但**并没有规定一个固定的最低年数**。在工程实践里，通常可按以下粒度选择：

1. 1 年：仅适合开发调试、方法验证或粗略演示，不适合做最终选址判断。
2. 3-5 年：适合区域初筛和备选区比较，能够初步平滑年际波动。
3. 5-10 年：更常见于正式宏观选址和投资前比较，稳健性明显好于单年。
4. 10 年以上：若数据和算力允许，更适合高确定性评估，因为风资源本身存在显著年际变率。

因此，若问题是“实际应用一般选几年”，比较稳妥的工程答案是：**至少 3-5 年，正式选址更建议 5-10 年；1 年通常只用于测试或快速筛查。**

---

### 3.2 Exclusion 阶段（空间约束与可开发面积聚合）

在 reV 的实现中，空间约束（exclusions）与技术映射（techmap）在 `supply-curve-aggregation` 阶段耦合执行：

- 先按 `excl_dict` 对高分辨率栅格做空间排除/加权
- 再将可开发像素映射并聚合到供应曲线分辨率

因此，本手册将该步骤归入 Exclusion 主阶段。

#### 3.2.1 Supply-Curve-Aggregation（供应曲线聚合）

**目的**：在粗分辨率格网（如 64×64 像素 ≈ 4km × 64 = 256km 格网）内，聚合高分辨率 generation 结果，同时应用排除图层，输出每个格网单元的有效发电潜力。

**核心类**：`reV.supply_curve.sc_aggregation.SupplyCurveAggregation`

**必须输入**：

| 参数 | 说明 |
| --- | --- |
| `excl_fpath` | 排除层 HDF5 文件路径 |
| `tm_dset` | HDF5 文件中的 techmap 数据集名称（如 `"techmap_wtk"`） |
| `gen_fpath` | Generation 输出文件或 `"PIPELINE"` |
| `cf_dset` | Generation 文件中的容量系数数据集名（如 `"cf_mean-means"`） |
| `res_class_dset` | 用于资源等级分类的数据集（如 `"cf_mean-means"`） |
| `res_class_bins` | 资源等级边界（如 `[0, 0.2, 0.3, 1.0]`） |
| `resolution` | 聚合分辨率（格网中的像素数，通常 64） |

**`excl_dict` 格式**（排除规则）：

```python
excl_dict = {
    # 按值排除（1=受保护区域）
    "ri_padus": {
        "exclude_values": [1],
        "exclude_nodata": False
    },
    # 按范围包含（坡度 ≤ 5°）
    "ri_srtm_slope": {
        "inclusion_range": (None, 5),
        "exclude_nodata": False
    },
    # 加权包含（不同值类型有不同权重）
    "smod": {
        "inclusion_weights": {"1": 0.5, "2": 1.0, "3": 1.0}
    }
}
```

**配置文件示例**（`config_sc_agg.json`）：

```json
{
  "excl_fpath": "./ri_exclusions.h5",
  "tm_dset": "techmap_wtk_ri_100",
  "gen_fpath": "PIPELINE",
  "cf_dset": "cf_mean",
  "lcoe_dset": "lcoe_fcr",
  "res_class_dset": "cf_mean",
  "res_class_bins": [0, 0.2, 0.3, 1.0],
  "resolution": 64,
  "power_density": 3.0,
  "excl_dict": {
    "ri_padus": {"exclude_values": [1], "exclude_nodata": false},
    "ri_srtm_slope": {"inclusion_range": [null, 5], "exclude_nodata": false}
  },
  "data_layers": {
    "slope": {"dset": "ri_srtm_slope", "method": "mean"},
    "reeds_region": {"dset": "ri_reeds_regions", "method": "mode"}
  },
  "log_directory": "./logs/",
  "execution_control": {
    "option": "local",
    "max_workers": 2
  }
}
```

**Python API 调用**：

```python
from reV.supply_curve.sc_aggregation import SupplyCurveAggregation

agg = SupplyCurveAggregation(
    excl_fpath="./ri_exclusions.h5",
    tm_dset="techmap_wtk_ri_100",
    excl_dict={
        "ri_padus": {"exclude_values": [1], "exclude_nodata": False},
    },
    resolution=64,
    gen_fpath="./wind_gen_2012.h5",
    cf_dset="cf_mean",
    res_class_dset="cf_mean",
    res_class_bins=[0, 0.2, 0.3, 1.0],
    power_density=3.0,
)
sc_df = agg.run(max_workers=2)
sc_df.to_csv("sc_agg.csv", index=False)
```

**关于 TechMap**：`tm_dset` 是排除层 HDF5 中预生成的技术映射数据集，将排除层的每个像素映射到 generation 输出的站点 GID。若不存在，可用 `res_fpath` 参数让 reV 自动生成（耗时较长），或使用 `TechMapping.run()` 预先生成：

```python
from reV.supply_curve.tech_mapping import TechMapping

TechMapping.run(
    "./ri_exclusions.h5",       # excl_fpath（位置参数）
    "./wtk/ri_100_wtk_2012.h5", # res_fpath（位置参数）
    dset="techmap_wtk_ri_100",  # 写入排除层 h5 中的数据集名
    max_workers=1,
)
```

**输出文件**（`*_sc_agg.csv`）：包含每个 SC 点的坐标、资源等级、有效区域面积、容量、LCOE、聚合的辅助数据层等列。

---

### 3.3 Supply Curve 阶段（成本叠加与排序）

#### 3.3.1 Supply-Curve（供应曲线输电定价）

**目的**：为每个 SC 点叠加输电接入成本，生成最终按 LCOE（含输电）排序的供应曲线，用于选址决策。

**核心类**：`reV.supply_curve.supply_curve.SupplyCurve`

**必须输入**：

| 参数 | 说明 |
| --- | --- |
| `sc_points` | SC-Aggregation 输出 CSV，或 `"PIPELINE"` |
| `trans_table` | 输电线路特征表 CSV（由 reVX 工具生成） |
| `fixed_charge_rate` | 固定费用率（资本回收因子，如 `0.096`） |

**输电成本参数**：

```json
{
  "transmission_costs": {
    "line_cost": 1000,
    "line_tie_in_cost": 200,
    "station_tie_in_cost": 50,
    "center_tie_in_cost": 10,
    "sink_tie_in_cost": 100,
    "available_capacity": 0.3
  }
}
```

**配置文件示例**：

```json
{
  "sc_points": "PIPELINE",
  "trans_table": "./ri_trans_table.csv",
  "fixed_charge_rate": 0.096,
  "simple": false,
  "transmission_costs": {
    "line_cost": 1000,
    "line_tie_in_cost": 200,
    "station_tie_in_cost": 50,
    "center_tie_in_cost": 10,
    "sink_tie_in_cost": 100,
    "available_capacity": 0.3
  },
  "log_directory": "./logs/",
  "execution_control": {"option": "local"}
}
```

> ⚠️ `trans_table` 不包含在 reV 代码仓库中，需使用 [reVX](https://github.com/NREL/reVX) 工具的 `TransmissionCosts` 从输电线路 GIS 数据生成。测试用途可设 `"simple": true`，使用简化定价。

---

#### 3.3.2 Rep-Profiles（代表性时间序列）

**目的**：从聚合区域内所有站点的 `cf_profile` 中，为每个 SC 区域（按 `reg_cols` 分组）挑选 N 个最具代表性的发电时序，用于后续电网规划和生产模拟。

**核心类**：`reV.rep_profiles.rep_profiles.RepProfiles`

**必须输入**：

| 参数 | 说明 |
| --- | --- |
| `gen_fpath` | Generation 输出文件（含 `cf_profile` 数据集），或 `"PIPELINE"` |
| `rev_summary` | SC-Aggregation 输出 CSV，或 `"PIPELINE"` |
| `cf_dset` | 时序数据集名，多年时格式如 `"cf_profile-{}"` |
| `reg_cols` | 分组列名列表（如 `["reeds_region", "res_class"]`） |

**配置文件示例**：

```json
{
  "gen_fpath": "PIPELINE",
  "rev_summary": "PIPELINE",
  "cf_dset": "cf_profile",
  "reg_cols": ["reeds_region", "res_class"],
  "n_profiles": 5,
  "rep_method": "meanoid",
  "err_method": "rmse",
  "log_directory": "./logs/",
  "execution_control": {"option": "local", "max_workers": 2}
}
```

`rep_method` 选项：`"meanoid"`（最接近均值）、`"powermean"`  

`err_method` 选项：`"rmse"`、`"mape"`

---

#### 3.3.3 QA-QC（质量检查）

**目的**：对任意步骤的输出做自动化质量检查，生成统计图和报告。完全可选。

**配置文件示例**：

```json
{
  "modules": ["generation", "supply-curve-aggregation"],
  "generation": {
    "fpath": "PIPELINE",
    "dsets": ["cf_mean"],
    "low_res_kwargs": {"resolution": 4}
  },
  "log_directory": "./logs/",
  "execution_control": {"option": "local"}
}
```

---

## 4. 阶段顺序与可选性矩阵

| 步骤 | 必须/可选 | 触发条件 | 前置依赖 | 顺序可调？ |
| --- | --- | --- | --- | --- |
| Generation | **必须** | 始终运行 | 无 | 起点，不可移动 |
| Collect | 可选 | 上游产生多个分片输出时（最常见为多节点/多批次并行） | Generation | 不可调（若需要则紧跟 Gen） |
| Multi-Year | 可选 | 需要汇总两个及以上年份结果时 | Generation 或 Collect | 不可调（若需要则在 Gen/Collect 后、SC-Agg 前） |
| SC-Aggregation | **必须**（宏观选址） | 需要空间聚合 | Generation / Collect / Multi-Year | 不可调 |
| Supply-Curve | 可选 | 需要输电成本 | SC-Aggregation | 不可调 |
| Rep-Profiles | 可选 | 需要代表性时序 | Generation（或 Multi-Year） + SC-Aggregation | 不可调（需两者输出） |
| QA-QC | 可选 | 任何时候 | 被检查步骤的输出 | 可在任意步骤后插入 |

**最小化风电宏观选址流程**（单年，本地运行）：

```
Generation → SC-Aggregation → Supply-Curve
```

**完整流程**（多年，HPC 集群）：

```
Generation → Collect → Multi-Year → SC-Aggregation → Supply-Curve → Rep-Profiles → QA-QC
```

---

## 5. Bespoke 风场布局优化（替代路径）

Bespoke 是 reV 的**风电专属替代流程**，在单个供应曲线格网单元（SC point）内，将遗传算法布局优化与 SAM 能量仿真深度耦合。它**同时替代**标准流程中的 `generation` 模块和 `supply-curve-aggregation` 模块，直接为每个格网单元输出最优风机布局及对应的容量、AEP 和成本指标。

**在完整 Pipeline 中的位置**：

```
# 标准路径
generation → collect → multi-year → supply-curve-aggregation → supply-curve → rep-profiles

# Bespoke 替代路径
bespoke ─────────────────────────────────────────────────────→ supply-curve → rep-profiles
```

`bespoke` 之后仍需运行 `supply-curve`（叠加输电成本）和可选的 `rep-profiles`（提取代表性时序），这两个步骤与标准路径完全相同。

**与标准流程的对比**：

| 方面 | 标准 Pipeline | Bespoke |
| --- | --- | --- |
| 风机布局 | 均匀功率密度假设（无布局优化） | 遗传算法在可建设多边形内动态优化 |
| 能量计算粒度 | 每个资源点独立计算，之后聚合 | 每个 SC 格网单元整体建模（含尾流） |
| 适用场景 | 大区域快速筛选（省级/国家级） | 精细化项目开发评估（场址级） |
| 计算成本 | 低（每站点几秒） | 高（每格网单元数分钟至数小时） |
| 输出格式 | Generation `.h5` + SC-Agg `.csv` | 包含布局坐标 (`turbine_x_coords`, `turbine_y_coords`) 的 `.h5` |
| 前置步骤 | 无（SC-Agg 自动或预先生成 TechMap） | 必须先运行 `TechMapping.run()` 生成 `tm_dset` |
| 多年分析 | 通过 `multi-year` 模块处理 | 通过 `res_fp` 通配符（如 `wtk_{}.h5` → `wtk_*`）原生支持 |

**核心类**：

- `reV.bespoke.bespoke.BespokeSinglePlant`：优化单个 SC 格网单元
- `reV.bespoke.bespoke.BespokeWindPlants`：批量优化多个 SC 格网单元（生产级 CLI）

**BespokeSinglePlant 构造函数关键参数**：

```python
BespokeSinglePlant(
    gid,                            # int：SC 格网单元 GID（techmap 中的编号）
    excl,                           # str | ExclusionMask：排除层 HDF5 文件路径
    res,                            # str | Resource：风资源 HDF5 路径（支持通配符多年）
    tm_dset,                        # str：排除层 HDF5 中的 techmap 数据集名
    sam_sys_inputs,                 # dict：SAM 风电配置（不含 wind_resource_filename）
    objective_function,             # str：目标函数表达式（最小化），如 "cost / aep"
    capital_cost_function,          # str：资本成本函数（$），如 "200 * system_capacity"
    fixed_operating_cost_function,  # str：固定运维成本（$/年），如 "0.01 * capital_cost"
    variable_operating_cost_function,  # str：可变运维成本（$/kWh），如 "0"
    balance_of_system_cost_function,   # str：平衡系统成本（$），如 "0"
    min_spacing='5x',               # 最小机间距（m 或 "Nx" 倍叶轮直径）
    ga_kwargs=None,                 # 遗传算法参数 dict，如 {"max_time": 60}
    output_request=('system_capacity', 'cf_mean'),  # 输出请求
    excl_dict=None,                 # 排除规则 dict
    resolution=64,                  # SC 聚合分辨率（像素数/轴）
)
```

> **注意**：目标函数和成本函数均为字符串表达式，由 `eval` 在运行时执行。可用变量包括 `n_turbines`、`system_capacity`（kW）、`aep`（kWh/yr）、`capital_cost`、`fixed_operating_cost`、`variable_operating_cost`、`balance_of_system_cost`、`avg_sl_dist_to_center_m`、`avg_sl_dist_to_medoid_m` 等。

### 5.1 说法准确性核验（含出处）

针对“`bespoke` 位于 exclusion 之后、supply curve 之前，且是在宏观选址基础上做微观选址以提升精度”的说法，可拆分为两部分：

1. **基本准确**：`bespoke` 的输入明确依赖 exclusion 和 `tm_dset`，且优化对象是 supply curve point。
2. **需要限定**：`bespoke` 在官方流程中属于**可选分支**，不是默认 full pipeline 的固定必经步骤。

**核验结论**：

- `bespoke` 与 exclusion 的关系：准确。`BespokeSinglePlant` 构造参数包含 `excl` 与 `tm_dset`，语义上就是“针对单个 supply curve point 的优化”。
- `bespoke` 与 supply curve 的关系：在工程实践中，常作为 supply-curve 之前的微观优化步骤，然后再进入 `supply-curve` 叠加输电成本。
- “固定流程位置”这一点：不应绝对化。官方 full pipeline 示例默认路径并不包含 `bespoke`，说明它是可选替代/增强路径，而非默认标准步骤。

**源码与仓库文档出处**：

- `reV/bespoke/bespoke.py`
  - 类说明：`BespokeSinglePlant` 用于单个 supply curve point
  - 参数说明：`gid` 是 supply curve point 的 gid；`tm_dset` 为 exclusions-to-resource 映射数据集
  - `BespokeWindPlants` 说明：`project_points` 指向的是 supply curve GID，而非 generation 资源 GID
- `examples/full_pipeline_execution/config_pipeline.json`
  - 默认 full pipeline 为 `generation -> collect -> multi-year -> supply-curve-aggregation -> supply-curve -> rep-profiles -> qa-qc`
  - 该默认示例中未包含 `bespoke` 步骤
- `docs/source/_cli/cli.rst`
  - `reV bespoke` 作为独立 CLI 命令与其他模块并列，体现其模块化可选属性

**在线文档出处**：

- reV Project Points: <https://natlabrockies.github.io/reV/misc/examples.project_points.html>
- reV collect CLI: <https://natlabrockies.github.io/reV/_cli/reV%20collect.html>
- reV multi-year CLI: <https://natlabrockies.github.io/reV/_cli/reV%20multi-year.html>
- Full Pipeline Execution: <https://natlabrockies.github.io/reV/misc/examples.full_pipeline_execution.html>

**推荐表述（可直接引用）**：

`bespoke` 通常作为可选的微观优化分支，常见于 exclusion/techmap 确定可开发 SC 点之后、`supply-curve` 计算之前，用于在宏观筛选基础上优化机位布局并提升场址级评估精度；但它不是默认 full pipeline 的必经步骤。

---

## 6. 可运行示例

### 6.1 本地单年风电 Pipeline

以下示例完全使用 reV 代码库内置测试数据（`tests/data/`），无需下载任何外部数据。

**准备目录结构**：

```
wind_example/
├── config_gen.json
├── config_sc_agg.json
├── config_sc.json
├── config_pipeline.json
└── run.py
```

**`config_gen.json`**：

```json
{
  "technology": "windpower",
  "project_points": "TESTDATADIR/project_points/ri.csv",
  "sam_files": {"default": "TESTDATADIR/SAM/i_windpower.json"},
  "resource_file": "TESTDATADIR/wtk/ri_100_wtk_2012.h5",
  "output_request": ["cf_mean", "cf_profile"],
  "log_directory": "./logs/",
  "log_level": "INFO",
  "execution_control": {
    "option": "local",
    "max_workers": 2,
    "sites_per_worker": 50
  }
}
```

**`config_sc_agg.json`**：

```json
{
  "excl_fpath": "TESTDATADIR/ri_exclusions/ri_exclusions.h5",
  "tm_dset": "techmap_wtk_ri_100",
  "gen_fpath": "PIPELINE",
  "cf_dset": "cf_mean",
  "res_class_dset": "cf_mean",
  "res_class_bins": [0, 0.2, 0.3, 1.0],
  "resolution": 64,
  "power_density": 3.0,
  "excl_dict": {
    "ri_padus": {"exclude_values": [1], "exclude_nodata": false}
  },
  "log_directory": "./logs/",
  "execution_control": {"option": "local", "max_workers": 2}
}
```

**完整 Python 运行脚本（`run.py`）**：

```python
#!/usr/bin/env python
"""
本地单年风电宏观选址完整流程示例
使用 reV 内置测试数据（无需下载）
"""
import os
import tempfile
import shutil

import numpy as np
import pandas as pd

from reV import TESTDATADIR
from reV.generation.generation import Gen
from reV.supply_curve.sc_aggregation import SupplyCurveAggregation
from reV.supply_curve.tech_mapping import TechMapping

# ─────────────────── 0. 准备文件路径 ───────────────────
YEAR = 2012
PP_CSV = os.path.join(TESTDATADIR, "project_points/ri.csv")
SAM_JSON = os.path.join(TESTDATADIR, "SAM/i_windpower.json")
RES_FILE = os.path.join(TESTDATADIR, f"wtk/ri_100_wtk_{YEAR}.h5")
EXCL_FILE = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
TM_DSET = "techmap_wtk_ri_100"

EXCL_DICT = {
    "ri_padus": {"exclude_values": [1], "exclude_nodata": False},
    "ri_smod": {"inclusion_range": (None, 3), "exclude_nodata": False},
}

out_dir = "./wind_output"
os.makedirs(out_dir, exist_ok=True)

# ─────────────────── 1. TechMapping ───────────────────
# 如果排除层 h5 中还没有 techmap，先生成
# 注意：会直接写入 EXCL_FILE，建议先 copy 到工作目录
excl_copy = os.path.join(out_dir, "ri_exclusions.h5")
if not os.path.exists(excl_copy):
    shutil.copy(EXCL_FILE, excl_copy)

# excl_fpath 和 res_fpath 是位置参数，也可以用关键字传递
TechMapping.run(
    excl_copy,                # excl_fpath
    RES_FILE,                 # res_fpath
    dset=TM_DSET,
    max_workers=1,
)
print("✓ TechMapping 完成")

# ─────────────────── 2. Generation ───────────────────
gen_out = os.path.join(out_dir, f"wind_gen_{YEAR}.h5")
if not os.path.exists(gen_out):
    # max_workers 和 out_fpath 是 Gen.run() 的参数，不在 Gen.__init__() 中
    gen = Gen(
        technology="windpower",
        project_points=PP_CSV,
        sam_files={"default": SAM_JSON},
        resource_file=RES_FILE,
        output_request=("cf_mean", "cf_profile"),
        sites_per_worker=50,
    )
    gen.run(out_fpath=gen_out, max_workers=2)
    print(f"✓ Generation 完成 → {gen_out}")
else:
    print(f"✓ Generation 已存在，跳过")

# ─────────────────── 3. SC-Aggregation ───────────────────
sc_agg_out = os.path.join(out_dir, "wind_sc_agg.csv")
agg = SupplyCurveAggregation(
    excl_fpath=excl_copy,
    tm_dset=TM_DSET,
    excl_dict=EXCL_DICT,
    resolution=64,
    gen_fpath=gen_out,
    cf_dset="cf_mean",
    res_class_dset="cf_mean",
    res_class_bins=[0, 0.2, 0.3, 1.0],
    power_density=3.0,
)
sc_df = agg.run(max_workers=2)
sc_df.to_csv(sc_agg_out, index=False)
print(f"✓ SC-Aggregation 完成 → {sc_agg_out}")
print(f"  SC 点数量: {len(sc_df)}")
print(f"  列: {list(sc_df.columns)}")

# ─────────────────── 4. （可选）分析结果 ───────────────────
sc_df = pd.read_csv(sc_agg_out)
print("\n供应曲线摘要：")
print(sc_df[["latitude", "longitude", "capacity", "mean_cf", "res_class"]].head(10))
```

**使用 reV pipeline CLI 运行**（需 JSON 配置）：

```bash
# 在配置目录中
reV pipeline -c config_pipeline.json --monitor
```

`config_pipeline.json` 示例：

```json
{
  "logging": {"log_level": "INFO"},
  "pipeline": [
    {"generation": "./config_gen.json"},
    {"supply-curve-aggregation": "./config_sc_agg.json"},
    {"supply-curve": "./config_sc.json"}
  ]
}
```

---

### 6.2 Bespoke 风场布局优化

直接基于仓库示例 `examples/bespoke_wind_plants/single_run.py`，以下是可运行的完整示例：

```python
#!/usr/bin/env python
"""
Bespoke 风场布局优化示例
使用遗传算法在排除区域内优化风机布局

API 注意事项（基于 reV.bespoke.bespoke.BespokeSinglePlant）：
- 前 5 个参数（gid, excl, res, tm_dset, sam_sys_inputs）为位置参数
- objective_function 之后须提供 4 个独立成本函数字符串（positional）
- res_fp 支持通配符，用于多年资源文件（如 'wtk_{}.h5' 格式拷贝后替换为 'wtk_*.h5'）
"""
import json
import os
import shutil
import tempfile

import numpy as np

from reV import TESTDATADIR
from reV.bespoke.bespoke import BespokeSinglePlant
from reV.supply_curve.tech_mapping import TechMapping

# ─── 数据文件路径 ───
SAM_FILE = os.path.join(TESTDATADIR, "SAM/i_windpower.json")
EXCL_FILE = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
RES_FILE_TMPL = os.path.join(TESTDATADIR, "wtk/ri_100_wtk_{}.h5")
TM_DSET = "techmap_wtk_ri_100"

# ─── 加载并修改 SAM 配置 ───
with open(SAM_FILE) as f:
    sam_sys_inputs = json.load(f)

sam_sys_inputs["wind_farm_wake_model"] = 2       # Park/WAsP 尾流模型
sam_sys_inputs["wind_farm_losses_percent"] = 0
del sam_sys_inputs["wind_resource_filename"]     # 由 reV 自动注入，不能手动设置

# ─── 排除规则 ───
excl_dict = {
    "ri_srtm_slope": {"inclusion_range": (None, 5), "exclude_nodata": False},
    "ri_padus": {"exclude_values": [1], "exclude_nodata": False},
    "ri_reeds_regions": {"inclusion_range": (None, 400), "exclude_nodata": False},
}

# ─── 目标函数与成本函数（字符串表达式，由 eval 执行）───
# objective_function: 遗传算法最小化的目标
# capital_cost_function: 资本成本（$）
# fixed_operating_cost_function: 固定运维成本（$/年），传 "0" 表示忽略
# variable_operating_cost_function: 可变运维成本（$/kWh），传 "0" 表示忽略
# balance_of_system_cost_function: 平衡系统成本（$），传 "0" 表示忽略
objective_function = "cost / aep"
capital_cost_function = """200 * system_capacity * np.exp(
    -system_capacity / 1E5 * 0.1 + (1 - 0.1))"""
fixed_operating_cost_function = "0"
variable_operating_cost_function = "0"
balance_of_system_cost_function = "0"

output_request = ("system_capacity", "cf_mean", "cf_profile")
gid = 33  # 待优化的 SC 格网单元 GID

with tempfile.TemporaryDirectory() as td:
    # 复制到临时目录（TechMapping 会修改排除层文件，资源文件避免污染原始数据）
    excl_fp = os.path.join(td, "ri_exclusions.h5")
    res_fp_tmpl = os.path.join(td, "ri_100_wtk_{}.h5")
    shutil.copy(EXCL_FILE, excl_fp)
    shutil.copy(RES_FILE_TMPL.format(2012), res_fp_tmpl.format(2012))
    shutil.copy(RES_FILE_TMPL.format(2013), res_fp_tmpl.format(2013))

    # 步骤 1：生成 TechMap（写入 excl_fp 中的 TM_DSET 数据集）
    # 参数名: excl_fpath, res_fpath（不是 excl_fp / res_file）
    TechMapping.run(
        excl_fp,                         # excl_fpath（位置参数）
        RES_FILE_TMPL.format(2012),      # res_fpath（位置参数）
        dset=TM_DSET,
        max_workers=1,
    )

    # 步骤 2：运行 Bespoke 优化
    # 多年资源文件：将 {} 替换为 * 通配符，reV 使用 MultiYearWindResource 自动读取
    res_fp = res_fp_tmpl.format("*")

    bsp = BespokeSinglePlant(
        gid,                              # SC 格网单元 GID
        excl_fp,                          # excl：排除层文件路径
        res_fp,                           # res：资源文件路径（通配符）
        TM_DSET,                          # tm_dset
        sam_sys_inputs,                   # SAM 配置 dict
        objective_function,               # 目标函数（最小化）
        capital_cost_function,            # 资本成本函数 $
        fixed_operating_cost_function,    # 固定运维成本函数 $/yr
        variable_operating_cost_function, # 可变运维成本函数 $/kWh
        balance_of_system_cost_function,  # 平衡系统成本函数 $
        ga_kwargs={"max_time": 20},       # 遗传算法最大运行时间（秒）
        excl_dict=excl_dict,
        output_request=output_request,
    )
    results = bsp.run_plant_optimization()

# 输出结果
print(f"风机数量:        {results['n_turbines']}")
print(f"总装机容量 (kW): {results['system_capacity']:.1f}")
print(f"年发电量 AEP:    {results['bespoke_aep']:.2f} kWh/yr")
print(f"优化目标值:       {results['bespoke_objective']:.6f}")
print(f"资本成本 ($):    {results.get('bespoke_capital_cost', 'N/A')}")
```

> **常见问题**：
>
> - `wind_resource_filename` 必须从 SAM 配置中删除，否则 reV 无法注入资源数据。
> - `excl_fp` 需要复制到工作目录，`TechMapping.run()` 会直接修改该文件（写入 techmap）。
> - `res_fp` 通配符格式（`*`）由 `rex.MultiYearWindResource` 多年自动聚合。
> - 以上 5 个函数参数（`objective_function` 至 `balance_of_system_cost_function`）均为**必须提供的位置参数**，无默认值，不可省略；不需要的成本项传 `"0"` 即可。

### 6.3 官方示例核验与完整操作流程

**核验结论**：

1. `examples/full_pipeline_execution/` 是**逻辑完整**的官方全流程示例，但**不是自包含、开箱即跑**的示例。(其依赖网络上的数据，而且数据量比较大；运行模式为分布式集群模式）
2. 该示例中的数据引用在逻辑上是**前后一致**的：
   - `config_gen.json` 和 `config_aggregation.json` 都指向同一套 `/datasets/NSRDB/v3.0.1/nsrdb_{}.h5` 年度资源文件；
   - `nsrdb_conus_project_points.csv` 使用的是与 NSRDB 资源文件一致的 `gid`；
   - `config_aggregation.json` 使用 `tm_dset = "techmap_nsrdb"` 和 `resolution = 64`；
   - `config_supply-curve.json` 使用的输电表文件名为 `conus_trans_lines_cache_064_sj_infsink.csv`，其 `064` 与聚合分辨率 `64` 一致。
3. 该示例**无法直接运行**的原因是仓库中缺少至少 3 类关键输入：
   - NREL 内部或大体量外部资源文件 `/datasets/NSRDB/v3.0.1/nsrdb_{}.h5`
   - `rev_conus_exclusions.h5`
   - `conus_trans_lines_cache_064_sj_infsink.csv`
4. `examples/running_locally/`、`examples/single_module_execution/`、`examples/project_points/` 等官方示例只覆盖单模块或局部流程，不能单独构成完整 end-to-end 教学案例。
5. 对于当前仓库，**最适合做可复现实操示例的数据组合**不是 `examples/full_pipeline_execution/`，而是 `tests/data/` 中的 Rhode Island（RI）小样本风电数据。

**推荐的可复现数据组合（前后一致）**：

| 输入类型 | 推荐文件 | 用途 |
| --- | --- | --- |
| 风资源 | `tests/data/wtk/ri_100_wtk_2012.h5`、`tests/data/wtk/ri_100_wtk_2013.h5` | Generation / Multi-Year |
| 站点列表 | `tests/data/project_points/ri.csv` | Generation 输入 |
| 风机/SAM 配置 | `tests/data/SAM/i_windpower.json` | Generation 输入 |
| 排除层 | `tests/data/ri_exclusions/ri_exclusions.h5` | TechMapping / SC-Aggregation |
| 输电表 | `tests/data/trans_tables/ri_simple_transmission_table.csv` 或 `ri_transmission_table.csv` | Supply-Curve 输入 |

这套 Rhode Island 小数据在测试代码中被反复组合使用，适合作为教学和开发调试的完整流程输入。

#### 6.3.1 完整操作流程（推荐教学路径）

**步骤 0：准备工作目录**

- 新建一个独立工作目录，例如 `wind_pipeline_demo/`
- 将排除层文件复制到工作目录，因为 `TechMapping.run()` 会原地写入 `tm_dset`
- 准备 2 年风资源文件（例如 2012、2013），便于演示 `multi-year`

**步骤 1：准备 `project_points`**

如果直接使用仓库数据，可用 `tests/data/project_points/ri.csv`。如果你只有经纬度或区域边界，可以按官方支持方式动态生成：

```python
from reV.config.project_points import ProjectPoints

lat_lons = [
  [41.77, -71.74],
  [41.73, -71.70],
]

pp = ProjectPoints.lat_lon_coords(
  lat_lons,
  "./wtk/ri_100_wtk_2012.h5",
  "./SAM/i_windpower.json",
)
pp.df.to_csv("./project_points.csv", index=False)
```

如果已有州/县级筛选条件，也可以使用 `ProjectPoints.regions()` 从资源文件 `meta` 中提取 `gid`。

**步骤 2：运行 Generation**

- 输入：`project_points.csv` + `i_windpower.json` + `ri_100_wtk_2012.h5` / `ri_100_wtk_2013.h5`
- 输出：每个年份一个 Generation HDF5，至少请求 `cf_mean`；如果后续还要做 `rep-profiles`，应同时请求 `cf_profile`

```bash
reV generation -c config_gen.json
```

**步骤 3：如有分片输出，运行 Collect**

- 如果 Generation 已直接输出完整单文件，可跳过
- 如果上游生成了 `_nodeXX` 或其他 chunk 文件，则运行 Collect 合并

```bash
reV collect -c config_collect.json
```

**步骤 4：如有多个年份，运行 Multi-Year**

- 若只跑 1 年，可跳过
- 若跑了 2 年及以上，建议运行 `multi-year`，得到 `cf_mean-means`、`cf_mean-stdev` 等跨年统计量

```bash
reV multi-year -c config_multi-year.json
```

**步骤 5：准备 exclusion 并生成 techmap**

- 输入：`ri_exclusions.h5`
- 必要条件：排除层中必须有空间参考信息，且能够生成 `tm_dset`
- 常见做法：先复制排除层文件，再调用 `TechMapping.run()` 写入 `techmap_wtk_ri_100`

```python
from reV.supply_curve.tech_mapping import TechMapping

TechMapping.run(
  "./ri_exclusions.h5",
  "./wtk/ri_100_wtk_2012.h5",
  dset="techmap_wtk_ri_100",
  max_workers=1,
)
```

**步骤 6：运行 SC-Aggregation（Exclusion 阶段）**

- 输入：Generation 或 Multi-Year 输出 + exclusion HDF5 + `tm_dset`
- 输出：供应曲线聚合结果 CSV
- 如果用了多年数据，`cf_dset` 推荐设为 `cf_mean-means`

```bash
reV supply-curve-aggregation -c config_sc_agg.json
```

**步骤 7：运行 Supply-Curve**

- 输入：SC-Aggregation 输出 + transmission table
- 推荐教学用表：`tests/data/trans_tables/ri_simple_transmission_table.csv`
- 若要更接近真实工程，可用 `ri_transmission_table.csv`

```bash
reV supply-curve -c config_sc.json
```

**步骤 8：可选运行 Rep-Profiles 与 QA-QC**

- `rep-profiles` 依赖 `cf_profile` 和 SC-Aggregation 输出
- `qa-qc` 用于快速验证 Generation、SC-Aggregation 或 Supply-Curve 结果分布

```bash
reV rep-profiles -c config_rep-profiles.json
reV qa-qc -c config_qa-qc.json
```

#### 6.3.2 免费数据源与替代方案

**1. 风资源数据（有免费官方来源）**

- NREL WIND Toolkit 门户：<https://www.nlr.gov/grid/wind-toolkit.html>
- WIND Toolkit 开发者接口说明：<https://developer.nrel.gov/docs/wind/wind-toolkit/>
- reV 官方文档还给出了可直接通过 S3 访问的示例路径，例如：`s3://nrel-pds-wtk/conus/v1.0.0/wtk_conus_2007.h5`

**2. 排除层原始数据（有免费原始来源，但通常没有现成的 reV-ready HDF5）**

- PAD-US 保护地数据：<https://www.usgs.gov/programs/gap-analysis-project/pad-us-data-download>
- SRTM DEM / 坡度基础数据：<https://lpdaac.usgs.gov/products/srtmgl1v003/>
- OpenStreetMap 下载镜像（道路、居民地等）：<https://download.geofabrik.de/>

这些数据通常需要先下载 GeoTIFF / Shapefile / GeoPackage，再转换为 reV 可用的 exclusions HDF5。

**3. 输电表数据**

- 当前官方 `examples/full_pipeline_execution/` 没有提供可直接下载的自包含 `trans_table.csv`
- 教学和调试可直接使用仓库自带的 `tests/data/trans_tables/ri_simple_transmission_table.csv`
- 真实工程中通常需要使用 `reVX` 基于原始输电 GIS 数据生成 reV-ready 的 transmission table

**4. 如果没有真实数据，是否可以使用合成数据**

- 可以。资源 HDF5 可以使用本手册 [7.3](#73-生成合成风资源数据) 的代码生成
- 排除层 HDF5 可以使用本手册 [8.2](#82-排除层文件-hdf5-规范) 中的示例代码构造
- `project_points.csv` 可以由经纬度、区域筛选或人工指定 `gid` 列表生成

#### 6.3.3 数据格式转换代码入口

如果你的原始数据不是 reV 直接支持的格式，可使用以下代码模板：

- **NetCDF / xarray 风资源 → reV HDF5**：见 [8.3](#83-添加自定义数据接口) 中的 `netcdf_to_rev_h5()` 示例
- **GeoTIFF 排除层 → exclusions HDF5**：见 [8.2](#82-排除层文件-hdf5-规范) 中的 `geotiff_to_exclusion_h5()` 示例
- **经纬度 / 区域 → `project_points.csv`**：见本节步骤 1 的 `ProjectPoints.lat_lon_coords()` 与 `ProjectPoints.regions()` 示例

如果只是为了验证流程而非构建真实项目，优先建议使用 `tests/data/` 中的 RI 小样本数据，而不是从零开始拼接全国级公开数据。

---

## 7. 数据获取与合成数据生成

### 7.1 使用内置测试数据（推荐开发调试）

reV 代码库自带完整的 RI（罗德岛）小规模测试数据集，无需下载：

```python
from reV import TESTDATADIR
import os

# 风资源文件（WTK，100m 高度）
wtk_2012 = os.path.join(TESTDATADIR, "wtk/ri_100_wtk_2012.h5")  # 200 站点，8784 时步
wtk_2013 = os.path.join(TESTDATADIR, "wtk/ri_100_wtk_2013.h5")

# 排除层文件
excl = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
# 包含层：ri_padus, ri_reeds_regions, ri_smod, latitude, longitude

# SAM 风电配置
sam = os.path.join(TESTDATADIR, "SAM/i_windpower.json")

# 站点列表
pp = os.path.join(TESTDATADIR, "project_points/ri.csv")
```

### 7.2 下载真实 WTK 数据

**Wind Integration National Dataset Toolkit (WTK)**：

- **数据门户**：https://www.nrel.gov/grid/wind-toolkit.html
- **下载工具**：[HSDS（高性能存储服务）](https://github.com/HDFGroup/hsds) 或 [reV Peregrine](https://github.com/NREL/rex)
- **rex 直接访问**（需 API key）：

```python
# 通过 HSDS 远程访问（需配置 ~/.hscfg）
from rex import WindResource

with WindResource("/nrel/wtk/conus/wtk_conus_2012.h5", hsds=True) as wind:
    meta = wind.meta
    time_index = wind.time_index
    ws_100m = wind["windspeed_100m", :, 0:100]  # 前 100 个站点
```

- **批量下载**：使用 [NREL Wind Toolkit Downloader](https://github.com/NREL/sup3r) 或申请 Eagle HPC 直接访问

### 7.3 生成合成风资源数据

当无法获取真实数据时，可编程生成符合 rex 格式的合成 HDF5 文件：

```python
#!/usr/bin/env python
"""生成合成 WTK 风资源数据（用于测试）"""
import numpy as np
import pandas as pd
import h5py
from datetime import datetime, timezone

# ─── 参数 ───
N_SITES = 50          # 站点数
YEAR = 2023
N_TIME = 8760         # 非闰年

# ─── 创建 meta ───
lats = np.linspace(41.5, 42.0, N_SITES)
lons = np.linspace(-71.5, -71.0, N_SITES)
meta_df = pd.DataFrame({
    "latitude": lats,
    "longitude": lons,
    "country": "USA",
    "state": "Rhode Island",
    "county": "Providence",
    "timezone": -5,
    "elevation": np.random.uniform(0, 100, N_SITES),
    "offshore": 0,
})

# ─── 创建时间索引 ───
time_index = pd.date_range(
    f"{YEAR}-01-01 00:00:00",
    periods=N_TIME,
    freq="1h",
    tz="UTC",
)

# ─── 生成合成风速/风向数据 ───
# Weibull 分布模拟真实风速特性
rng = np.random.default_rng(42)
ws_100m = rng.weibull(2.0, size=(N_TIME, N_SITES)) * 8.0   # 均值约7.1 m/s
wd_100m = rng.uniform(0, 360, size=(N_TIME, N_SITES)).astype(np.float32)
tmp_100m = (15 + 10 * np.sin(np.linspace(0, 2 * np.pi, N_TIME))
            )[:, None] * np.ones((1, N_SITES))
pres_100m = np.full((N_TIME, N_SITES), 101325.0, dtype=np.float32)

# ─── 写入 HDF5 ───
output_file = f"synthetic_wtk_{YEAR}.h5"
with h5py.File(output_file, "w") as f:
    # meta（DataFrame 序列化为 numpy void / bytes）
    meta_bytes = meta_df.to_records(index=False)
    f.create_dataset("meta", data=meta_bytes)

    # time_index（ISO 8601 字符串数组）
    ti_bytes = np.array(
        [t.strftime("%Y-%m-%d %H:%M:%S+00:00").encode() for t in time_index]
    )
    f.create_dataset("time_index", data=ti_bytes)

    # 风速/风向/温度/气压（shape: (time, sites)）
    f.create_dataset("windspeed_100m", data=ws_100m.astype(np.float32),
                     chunks=(min(N_TIME, 100), min(N_SITES, 25)))
    f.create_dataset("winddirection_100m", data=wd_100m,
                     chunks=(min(N_TIME, 100), min(N_SITES, 25)))
    f.create_dataset("temperature_100m", data=tmp_100m.astype(np.float32))
    f.create_dataset("pressure_100m", data=pres_100m)

    # 全局属性
    f.attrs["version"] = "synthetic-1.0"

print(f"✓ 合成 WTK 数据已写入 {output_file}")
print(f"  站点数: {N_SITES}, 时步: {N_TIME}")
```

> ⚠️ **重要**：合成数据中 `meta` 的编码格式必须与 rex 期望的格式完全一致（结构化 numpy 数组），否则 `WindResource` 读取 `meta` 时会报错。推荐参考以下 rex 兼容写法：

```python
# rex 兼容的 meta 写法（使用 Outputs 类）
from rex import Outputs

with Outputs(output_file, "w") as out:
    out.meta = meta_df       # Outputs 类自动处理序列化
    out.time_index = time_index
    out["windspeed_100m"] = ws_100m.astype(np.float32)
    out["winddirection_100m"] = wd_100m
```

---

## 8. 输入数据格式支持

### 8.1 资源文件 HDF5 规范（rex）

reV 使用 `rex.resource.Resource`（及其子类 `WindResource`、`SolarResource`）读取所有资源文件。文件必须满足以下规范：

**必须数据集**：

| 数据集 | 格式 | 说明 |
| --- | --- | --- |
| `meta` | 结构化数组，含 `latitude`、`longitude`、`timezone`、`elevation` 字段 | 站点元数据 |
| `time_index` | 字节字符串数组，ISO 8601 格式，带 UTC 时区 | 时间轴 |
| `windspeed_{hub_height}m` | float32，shape `(T, N)` | 风速（m/s） |
| `winddirection_{hub_height}m` | float32，shape `(T, N)` | 风向（度） |

**可选数据集**（SAM 可能需要）：

- `temperature_{height}m`：气温（°C）
- `pressure_{height}m`：气压（Pa）
- `relativehumidity_{height}m`：相对湿度（%）

**约束条件**：

- 时间轴长度必须是 8760 的整数倍（即整年）
- 时间轴必须从每年 1 月 1 日 00:00 UTC 开始
- 风速/风向数据集名格式必须为 `windspeed_{N}m` / `winddirection_{N}m`，其中 `N` 与 SAM 配置的 `wind_turbine_hub_ht` 对应

**验证方法**：

```python
from rex import WindResource

with WindResource("your_wind_file.h5") as res:
    print("meta shape:", res.meta.shape)
    print("time_index length:", len(res.time_index))
    print("datasets:", list(res.h5.keys()))
    ws = res["windspeed_100m"]
    print("windspeed shape:", ws.shape)  # 应为 (8760, N)
```

### 8.2 排除层文件 HDF5 规范

排除层文件由 `reV.handlers.exclusions.ExclusionLayers` 读取，使用 `rex.resource.Resource` 底层。

**必须数据集**：

| 数据集 | 格式 | 说明 |
| --- | --- | --- |
| `latitude` | float64，shape `(H, W)` | 2D 空间格网纬度 |
| `longitude` | float64，shape `(H, W)` | 2D 空间格网经度 |
| `{layer_name}` | uint8/float32，shape `(1, H, W)` 或 `(H, W)` | 排除层数据 |

**HDF5 属性（profile）**：每个排除层数据集必须含 `profile` 属性，描述坐标参考系（CRS）和地理变换（GeoTransform），格式与 GDAL rasterio profile 兼容：

```python
import json

profile = {
    "driver": "GTiff",
    "dtype": "uint8",
    "width": 972,
    "height": 1434,
    "count": 1,
    "crs": "+proj=lcc +lat_1=29.5 +lat_2=45.5 +lat_0=23 +lon_0=-96",
    "transform": [90, 0, -71.88, 0, -90, 42.22],  # [res_x, 0, xmin, 0, -res_y, ymax]
}
# profile 存储为 JSON 字符串属性
```

**创建排除层文件（推荐方式）**：

```python
import numpy as np
import h5py
import json

H, W = 1000, 800  # 格网尺寸

# 生成示例格网坐标
lon_1d = np.linspace(-72, -71, W)
lat_1d = np.linspace(42, 41, H)
lon_2d, lat_2d = np.meshgrid(lon_1d, lat_1d)

# 创建排除层（0=排除，1=包含）
padus_layer = np.ones((H, W), dtype=np.uint8)  # 示例：全部可用
padus_layer[100:200, 100:200] = 0              # 在某区域设置排除

profile = json.dumps({
    "driver": "GTiff", "dtype": "uint8",
    "width": W, "height": H, "count": 1,
    "crs": "EPSG:4326",
    "transform": [lon_1d[1]-lon_1d[0], 0, lon_1d[0], 0, lat_1d[1]-lat_1d[0], lat_1d[0]]
})

with h5py.File("my_exclusions.h5", "w") as f:
    f.create_dataset("latitude", data=lat_2d.astype(np.float64))
    f.create_dataset("longitude", data=lon_2d.astype(np.float64))
    
    ds = f.create_dataset("padus", data=padus_layer[np.newaxis, :, :])
    ds.attrs["profile"] = profile

print("✓ 排除层文件创建完成")
```

**使用 rasterio 从 GeoTIFF 转换**（推荐处理真实 GIS 数据）：

```python
import rasterio
import h5py
import numpy as np
import json

def geotiff_to_exclusion_h5(tif_path: str, h5_path: str, layer_name: str):
    """将 GeoTIFF 排除层转换为 reV 兼容 HDF5 格式"""
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(np.uint8)
        transform = src.transform
        crs = src.crs.to_proj4()
        height, width = data.shape

        # 生成经纬度格网（使用仿射变换计算）
        cols = np.arange(width)
        rows = np.arange(height)
        col_grid, row_grid = np.meshgrid(cols, rows)
        xs, ys = rasterio.transform.xy(transform, row_grid, col_grid)
        
        profile_dict = {
            "driver": "GTiff", "dtype": "uint8",
            "width": width, "height": height, "count": 1,
            "crs": crs,
            "transform": list(transform)[:6]
        }

    with h5py.File(h5_path, "a") as f:  # "a" = append mode
        if "latitude" not in f:
            f.create_dataset("latitude", data=np.array(ys, dtype=np.float64))
        if "longitude" not in f:
            f.create_dataset("longitude", data=np.array(xs, dtype=np.float64))
        
        ds = f.create_dataset(layer_name, data=data[np.newaxis, :, :])
        ds.attrs["profile"] = json.dumps(profile_dict)

    print(f"✓ 转换完成: {tif_path} → {h5_path}[{layer_name}]")
```

### 8.3 添加自定义数据接口

reV 通过 `rex.resource.Resource` 及其子类统一读取资源文件。若需要支持非 HDF5 格式（如 NetCDF、Zarr、CSV），有两种方案：

#### 方案 A：预处理转换为 rex HDF5（推荐）

最简单的集成方式，一次性将现有数据转换：

```python
import xarray as xr
import pandas as pd
import numpy as np
from rex import Outputs

def netcdf_to_rev_h5(nc_path: str, out_h5: str, hub_height: int = 100):
    """将 NetCDF 风数据转换为 reV 兼容 HDF5"""
    ds = xr.open_dataset(nc_path)
    
    # 提取空间维度
    lats = ds.latitude.values
    lons = ds.longitude.values
    
    # 构建 meta DataFrame
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    n_sites = lat_grid.size
    meta = pd.DataFrame({
        "latitude": lat_grid.ravel(),
        "longitude": lon_grid.ravel(),
        "timezone": 0,
        "elevation": 0.0,
        "offshore": 0,
    })
    
    # 提取时间轴
    time_index = pd.DatetimeIndex(ds.time.values).tz_localize("UTC")
    
    # 提取风速/风向数据，reshape 为 (time, sites)
    ws_var = f"ws{hub_height}"  # 根据实际变量名调整
    wd_var = f"wd{hub_height}"
    ws = ds[ws_var].values.reshape(len(time_index), n_sites)
    wd = ds[wd_var].values.reshape(len(time_index), n_sites)
    
    with Outputs(out_h5, "w") as out:
        out.meta = meta
        out.time_index = time_index
        out[f"windspeed_{hub_height}m"] = ws.astype(np.float32)
        out[f"winddirection_{hub_height}m"] = wd.astype(np.float32)
    
    print(f"✓ 转换完成: {nc_path} → {out_h5}")
    ds.close()
```

#### 方案 B：自定义 rex Resource 子类

若需要在运行时动态读取非 HDF5 格式，可继承 `rex.resource.Resource` 并重写关键方法。这是**侵入性较低**的集成方式：

```python
import pandas as pd
import numpy as np
import xarray as xr
from rex.resource import Resource


class NetCDFWindResource(Resource):
    """
    可直接传入 reV Generation 的自定义资源读取器
    
    继承 rex.Resource，重写数据访问接口以读取 NetCDF 文件。
    reV Generation 通过 duck typing 调用以下属性/方法：
    - .meta → pd.DataFrame，含 latitude, longitude, timezone, elevation
    - .time_index → pd.DatetimeIndex (UTC)
    - .__getitem__(dataset) → np.ndarray, shape (time, sites)
    - .close()
    """

    def __init__(self, nc_path: str, hub_height: int = 100, **kwargs):
        self._nc_path = nc_path
        self._hub_height = hub_height
        self._ds = xr.open_dataset(nc_path)
        self._meta = None
        self._time_index = None

    @property
    def meta(self) -> pd.DataFrame:
        if self._meta is None:
            lats = self._ds.latitude.values
            lons = self._ds.longitude.values
            lat_g, lon_g = np.meshgrid(lats, lons, indexing="ij")
            self._meta = pd.DataFrame({
                "latitude": lat_g.ravel(),
                "longitude": lon_g.ravel(),
                "timezone": 0,
                "elevation": 0.0,
                "offshore": 0,
            })
        return self._meta

    @property
    def time_index(self) -> pd.DatetimeIndex:
        if self._time_index is None:
            self._time_index = pd.DatetimeIndex(
                self._ds.time.values
            ).tz_localize("UTC")
        return self._time_index

    def __getitem__(self, dataset: str) -> np.ndarray:
        """
        dataset 格式样例：
        - "windspeed_100m" → ws100
        - "winddirection_100m" → wd100
        """
        n_sites = len(self.meta)
        n_times = len(self.time_index)
        
        if dataset.startswith("windspeed"):
            height = int(dataset.split("_")[1].rstrip("m"))
            arr = self._ds[f"ws{height}"].values
        elif dataset.startswith("winddirection"):
            height = int(dataset.split("_")[1].rstrip("m"))
            arr = self._ds[f"wd{height}"].values
        elif dataset.startswith("temperature"):
            arr = self._ds["temperature"].values
        else:
            raise KeyError(f"Dataset not available: {dataset}")
        
        return arr.reshape(n_times, n_sites).astype(np.float32)

    def close(self):
        self._ds.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── 使用方法 ───
# reV Generation 通过 resource_file 参数接受文件路径，并调用 check_res_file 判断类型。
# 目前 reV 没有公开的"注册自定义 Resource 类"接口。
# 推荐做法：继承 Gen 类并重写 _parse_res_file 方法，或使用"方案 A"预先转换。
```

> ⚠️ **注意**：目前 reV 的 `Gen` 类通过 `rex.utilities.utilities.check_res_file` 自动判断 HDF5 还是多文件资源，没有插件注册机制。自定义 Resource 子类需要通过**修改 `Gen._parse_res_file` 或 monkey-patching** 注入。最简单可靠的方式仍然是**方案 A（预处理转换）**。

---

## 9. 关键 API 参考索引

| 类/函数 | 文件 | 说明 |
| --- | --- | --- |
| `Gen` | `reV/generation/generation.py` | 发电量模拟入口 |
| `collect` CLI 入口 | `reV/handlers/cli_collect.py` | Collect 步骤入口；实际合并逻辑委托给 `gaps` |
| `MultiYear` | `reV/handlers/multi_year.py` | 多年汇总与跨年统计 |
| `SupplyCurveAggregation` | `reV/supply_curve/sc_aggregation.py` | SC 聚合 |
| `SupplyCurve` | `reV/supply_curve/supply_curve.py` | SC 输电定价 |
| `RepProfiles` | `reV/rep_profiles/rep_profiles.py` | 代表性时序 |
| `TechMapping` | `reV/supply_curve/tech_mapping.py` | 技术映射生成 |
| `BespokeSinglePlant` | `reV/bespoke/bespoke.py` | 单格网 Bespoke 优化 |
| `BespokeWindPlants` | `reV/bespoke/bespoke.py` | 批量 Bespoke 优化 |
| `ExclusionLayers` | `reV/handlers/exclusions.py` | 排除层读取 |
| `Outputs` | `reV/handlers/outputs.py` | reV HDF5 输出 |
| `ProjectPoints` | `reV/config/project_points.py` | 站点列表管理 |
| `SupplyCurveField` | `reV/utilities/__i__nit__.__py` | SC 输出列名枚举 |
| `ResourceMetaField` | `reV/utilities/__i__nit__.__py` | 资源 meta 列名枚举 |
| `TESTDATADIR` | `reV/__i__nit__.__py` | 测试数据目录路径 |

**reV CLI 命令**：

```bash
reV generation -c config_gen.json
reV collect -c config_collect.json
reV multi-year -c config_multi-year.json
reV supply-curve-aggregation -c config_sc_agg.json
reV supply-curve -c config_sc.json
reV rep-profiles -c config_rep-profiles.json
reV qa-qc -c config_qa-qc.json
reV pipeline -c config_pipeline.json --monitor
```

**配置文件通用字段**：

```jsonc
{
  "log_directory": "./logs/",
  "log_level": "INFO",
  "execution_control": {
    "option": "local",
    "max_workers": 4,
    "nodes": 1,
    "allocation": "rev",
    "walltime": 4.0
  }
}
```

> `option` 可选展: `"local"` | `"slurm"` | `"eagle"` | `"kestrel"`
>
> `max_workers`: 本地并行工作进程数
>
> `nodes`: HPC 节点数，`allocation`: HPC 账号（SLURM 时使用）

**`"PIPELINE"` 占位符**：在 pipeline 模式下，`"gen_fpath": "PIPELINE"` 等字段由 `gaps.pipeline.parse_previous_status()` 自动解析为前一步骤的输出文件路径，**不要在单步运行时使用**。

---

*文档版本：基于 reV 主分支代码（2024）。如有 API 变更，请以源码为准。*
