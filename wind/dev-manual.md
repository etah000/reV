# reV 风电场宏观选址开发手册

> 目标受众：软件工程师。本手册聚焦于 reV 风电场宏观选址（Wind Farm Macro Siting）的完整流程，覆盖每个步骤的输入输出、可调整顺序、可选性分析、可运行示例以及数据格式支持。

---

## 目录

1. [概述](#1-概述)
2. [完整流程图](#2-完整流程图)
3. [流程各步骤详解](#3-流程各步骤详解)
   - 3.1 [Generation（发电量模拟）](#31-generation发电量模拟)
   - 3.2 [Collect（分片合并）](#32-collect分片合并)
   - 3.3 [Multi-Year（多年均值）](#33-multi-year多年均值)
   - 3.4 [Supply-Curve-Aggregation（供应曲线聚合）](#34-supply-curve-aggregation供应曲线聚合)
   - 3.5 [Supply-Curve（供应曲线输电定价）](#35-supply-curve供应曲线输电定价)
   - 3.6 [Rep-Profiles（代表性时间序列）](#36-rep-profiles代表性时间序列)
   - 3.7 [QA-QC（质量检查）](#37-qa-qc质量检查)
4. [步骤顺序与可选性矩阵](#4-步骤顺序与可选性矩阵)
5. [Bespoke 风场布局优化（替代路径）](#5-bespoke-风场布局优化替代路径)
6. [可运行示例](#6-可运行示例)
   - 6.1 [本地单年风电 Pipeline（TESTDATADIR 数据）](#61-本地单年风电-pipeline)
   - 6.2 [Bespoke 风场布局优化](#62-bespoke-风场布局优化)
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
         │ (HPC 多节点时)
         ▼
┌─────────────────────────┐
│   2. Collect             │  → output_dir/*_gen_{year}.h5（合并分片）
│   (分片 HDF5 合并)       │
└─────────────────────────┘
         │ (多年运行时)
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

### 3.1 Generation（发电量模拟）

**目的**：对 `project_points` 中每个站点，调用 SAM `WindPower` 模块做逐小时物理模拟。

**核心类**：`reV.generation.generation.Gen`

**必须输入**：

| 参数 | 说明 |
|------|------|
| `technology` | `"windpower"` |
| `project_points` | 站点列表 CSV，至少含 `gid` 和 `config` 列 |
| `sam_files` | SAM 配置文件路径字典，key 与 `project_points.config` 对应 |
| `resource_file` | WTK 风资源 HDF5 文件路径，多年时用 `{}` 占位符 |

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
from reV.config.project_points import ProjectPoints

pp = ProjectPoints(
    "project_points_ri.csv",
    {"default": "sam_windpower.json"},
    "windpower",
    res_file="wtk/ri_100_wtk_2012.h5"
)

gen = Gen(
    "windpower",
    "project_points_ri.csv",
    {"default": "sam_windpower.json"},
    "wtk/ri_100_wtk_2012.h5",
    output_request=("cf_mean", "cf_profile"),
    sites_per_worker=25,
    max_workers=4,
)
gen.run()
# 输出文件自动写到当前目录下的 _gen_2012.h5
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

### 3.2 Collect（分片合并）

**目的**：HPC 集群并行运行时，每个节点产生一个 `_node{i}.h5` 分片，此步合并为完整文件。

**触发条件**：仅当 `execution_control.nodes > 1` 时需要。

**核心类**：`reV.handlers.collection.Collector`

**配置文件示例**（`config_collect.json`）：

```json
{
  "dsets": ["cf_mean", "cf_profile"],
  "file_type": "h5",
  "log_directory": "./logs/",
  "execution_control": {
    "option": "eagle",
    "nodes": 1,
    "allocation": "rev",
    "walltime": 1
  },
  "log_level": "INFO",
  "move_chunks": true,
  "project_points": "PIPELINE",
  "collect_pattern": "PIPELINE"
}
```

`"PIPELINE"` 占位符由 `gaps.pipeline` 自动从上一步状态文件解析。

---

### 3.3 Multi-Year（多年均值）

**目的**：对多个年份的 generation 输出，计算均值（`-means`）和标准差（`-stdev`），消除年际气候变率。

**触发条件**：仅当 `analysis_years` 包含多个年份时有意义。

**输出数据集命名约定**：

- `cf_mean-means`：跨年均值（后续 SC-Aggregation 用）
- `cf_mean-stdev`：跨年标准差
- `cf_profile-{year}`：各年完整时序

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

---

### 3.4 Supply-Curve-Aggregation（供应曲线聚合）

**目的**：在粗分辨率格网（如 64×64 像素 ≈ 4km × 64 = 256km 格网）内，聚合高分辨率 generation 结果，同时应用排除图层，输出每个格网单元的有效发电潜力。

**核心类**：`reV.supply_curve.sc_aggregation.SupplyCurveAggregation`

**必须输入**：

| 参数 | 说明 |
|------|------|
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
    excl_fpath="./ri_exclusions.h5",
    res_fpath="./wtk/ri_100_wtk_2012.h5",
    dset="techmap_wtk_ri_100",   # 写入排除层 h5 中的数据集名
    max_workers=1
)
```

**输出文件**（`*_sc_agg.csv`）：包含每个 SC 点的坐标、资源等级、有效区域面积、容量、LCOE、聚合的辅助数据层等列。

---

### 3.5 Supply-Curve（供应曲线输电定价）

**目的**：为每个 SC 点叠加输电接入成本，生成最终按 LCOE（含输电）排序的供应曲线，用于选址决策。

**核心类**：`reV.supply_curve.supply_curve.SupplyCurve`

**必须输入**：

| 参数 | 说明 |
|------|------|
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

### 3.6 Rep-Profiles（代表性时间序列）

**目的**：从聚合区域内所有站点的 `cf_profile` 中，为每个 SC 区域（按 `reg_cols` 分组）挑选 N 个最具代表性的发电时序，用于后续电网规划和生产模拟。

**核心类**：`reV.rep_profiles.rep_profiles.RepProfiles`

**必须输入**：

| 参数 | 说明 |
|------|------|
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

### 3.7 QA-QC（质量检查）

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

## 4. 步骤顺序与可选性矩阵

| 步骤 | 必须/可选 | 触发条件 | 前置依赖 | 顺序可调？ |
|------|-----------|----------|----------|-----------|
| Generation | **必须** | 始终运行 | 无 | 起点，不可移动 |
| Collect | 可选 | HPC 多节点并行时 | Generation | 不可调（必须紧跟 Gen） |
| Multi-Year | 可选 | 分析年份 ≥ 2 时 | Generation/Collect | 不可调（必须在 Gen 之后，SC-Agg 之前） |
| SC-Aggregation | **必须**（宏观选址） | 需要空间聚合 | Generation 或 Multi-Year | 不可调 |
| Supply-Curve | 可选 | 需要输电成本 | SC-Aggregation | 不可调 |
| Rep-Profiles | 可选 | 需要代表性时序 | Gen + SC-Aggregation | 不可调（需两者输出） |
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

Bespoke 是 reV 的**风电专属替代流程**，取代标准的 Generation + SC-Aggregation 步骤。它使用遗传算法在排除图层定义的不规则多边形区域内，优化每个格网单元的风机布局。

**与标准流程的对比**：

| 方面 | 标准 Pipeline | Bespoke |
|------|---------------|---------|
| 风机布局 | 固定网格（SAM 配置中预定义） | 遗传算法动态优化 |
| 适用场景 | 大区域快速筛选 | 精细化项目开发评估 |
| 计算成本 | 低（每站点几秒） | 高（每格网单元数分钟~小时） |
| 输出 | 标准 .h5 + CSV | 包含布局坐标的 .h5 |
| 前置步骤 | 无（但 SC-Agg 需 TechMap） | 必须先运行 `TechMapping.run()` |

**核心类**：`reV.bespoke.bespoke.BespokeSinglePlant`、`reV.bespoke.bespoke.BespokeWindPlants`

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

TechMapping.run(
    excl_fp=excl_copy,
    res_fpath=RES_FILE,
    dset=TM_DSET,
    max_workers=1,
)
print("✓ TechMapping 完成")

# ─────────────────── 2. Generation ───────────────────
gen_out = os.path.join(out_dir, f"wind_gen_{YEAR}.h5")
if not os.path.exists(gen_out):
    gen = Gen(
        technology="windpower",
        project_points=PP_CSV,
        sam_files={"default": SAM_JSON},
        resource_file=RES_FILE,
        output_request=("cf_mean", "cf_profile"),
        sites_per_worker=50,
        max_workers=2,
        out_fpath=gen_out,
    )
    gen.run()
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

此示例直接来自 `examples/bespoke_wind_plants/single_run.py`（已适配为完整文档）：

```python
#!/usr/bin/env python
"""
Bespoke 风场布局优化示例
使用遗传算法在排除区域内优化风机布局
"""
import json
import os
import shutil
import tempfile

import numpy as np

from reV import TESTDATADIR
from reV.bespoke.bespoke import BespokeSinglePlant
from reV.supply_curve.tech_mapping import TechMapping

# ─── 数据文件 ───
SAM_FILE = os.path.join(TESTDATADIR, "SAM/i_windpower.json")
EXCL_FILE = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
RES_FILE_TMPL = os.path.join(TESTDATADIR, "wtk/ri_100_wtk_{}.h5")
TM_DSET = "techmap_wtk_ri_100"

# ─── 加载并修改 SAM 配置 ───
with open(SAM_FILE) as f:
    sam_inputs = json.load(f)

sam_inputs["wind_farm_wake_model"] = 2       # 使用 Park wake 模型
sam_inputs["wind_farm_losses_percent"] = 0
del sam_inputs["wind_resource_filename"]     # 由 reV 自动注入
turb_rating = max(sam_inputs["wind_turbine_powercurve_powerout"])

# ─── 排除规则 ───
excl_dict = {
    "ri_srtm_slope": {"inclusion_range": (None, 5), "exclude_nodata": False},
    "ri_padus": {"exclude_values": [1], "exclude_nodata": False},
    "ri_reeds_regions": {"inclusion_range": (None, 400), "exclude_nodata": False},
}

# ─── 目标函数（字符串表达式，用 eval 执行）───
cost_fn = "200 * system_capacity * np.exp(-system_capacity / 1E5 * 0.1 + 0.9)"
obj_fn = "cost / aep"

with tempfile.TemporaryDirectory() as td:
    # 复制到临时目录（TechMapping 会修改排除层文件）
    excl_fp = os.path.join(td, "ri_exclusions.h5")
    res_fp_tmpl = os.path.join(td, "ri_100_wtk_{}.h5")
    shutil.copy(EXCL_FILE, excl_fp)
    for yr in (2012, 2013):
        shutil.copy(RES_FILE_TMPL.format(yr), res_fp_tmpl.format(yr))
    res_fp = res_fp_tmpl.format("*")   # 多年通配符

    # 步骤 1：生成 TechMap（写入 excl_fp 中的 TM_DSET 数据集）
    TechMapping.run(
        excl_fp=excl_fp,
        res_fpath=RES_FILE_TMPL.format(2012),
        dset=TM_DSET,
        max_workers=1,
    )

    # 步骤 2：运行 Bespoke 优化（gid=33 为格网单元 ID）
    bsp = BespokeSinglePlant(
        gid=33,
        excl_fp=excl_fp,
        res_fp=res_fp,
        tm_dset=TM_DSET,
        sam_sys_inputs=sam_inputs,
        objective_function=obj_fn,
        cost_function=cost_fn,
        ga_kwargs={"max_time": 30},    # 遗传算法最大运行时间（秒）
        excl_dict=excl_dict,
        output_request=("system_capacity", "cf_mean", "cf_profile"),
    )
    results = bsp.run_plant_optimization()

print(f"风机数量: {results['n_turbines']}")
print(f"总装机容量: {results['system_capacity']:.1f} kW")
print(f"年发电量(AEP): {results['bespoke_aep']:.2f} MWh/yr")
print(f"优化目标值: {results['bespoke_objective']:.4f}")
```

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
|--------|------|------|
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
|--------|------|------|
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
|---------|------|------|
| `Gen` | `reV/generation/generation.py` | 发电量模拟入口 |
| `Collector` | `reV/handlers/collection.py` | HDF5 分片合并 |
| `SupplyCurveAggregation` | `reV/supply_curve/sc_aggregation.py` | SC 聚合 |
| `SupplyCurve` | `reV/supply_curve/supply_curve.py` | SC 输电定价 |
| `RepProfiles` | `reV/rep_profiles/rep_profiles.py` | 代表性时序 |
| `TechMapping` | `reV/supply_curve/tech_mapping.py` | 技术映射生成 |
| `BespokeSinglePlant` | `reV/bespoke/bespoke.py` | 单格网 Bespoke 优化 |
| `BespokeWindPlants` | `reV/bespoke/bespoke.py` | 批量 Bespoke 优化 |
| `ExclusionLayers` | `reV/handlers/exclusions.py` | 排除层读取 |
| `Outputs` | `reV/handlers/outputs.py` | reV HDF5 输出 |
| `ProjectPoints` | `reV/config/project_points.py` | 站点列表管理 |
| `SupplyCurveField` | `reV/utilities/__init__.py` | SC 输出列名枚举 |
| `ResourceMetaField` | `reV/utilities/__init__.py` | 资源 meta 列名枚举 |
| `TESTDATADIR` | `reV/__init__.py` | 测试数据目录路径 |

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

```json
{
  "log_directory": "./logs/",
  "log_level": "INFO",
  "execution_control": {
    "option": "local",     // "local" | "slurm" | "eagle" | "kestrel"
    "max_workers": 4,      // 本地并行工作进程数
    "nodes": 1,            // HPC 节点数
    "allocation": "rev",   // HPC 账号（SLURM 时使用）
    "walltime": 4.0        // HPC 最大运行时间（小时）
  }
}
```

**`"PIPELINE"` 占位符**：在 pipeline 模式下，`"gen_fpath": "PIPELINE"` 等字段由 `gaps.pipeline.parse_previous_status()` 自动解析为前一步骤的输出文件路径，**不要在单步运行时使用**。

---

*文档版本：基于 reV 主分支代码（2024）。如有 API 变更，请以源码为准。*
