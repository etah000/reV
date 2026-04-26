# reV风电场宏观选址投标书技术说明

## 1. 编制说明

本文档用于说明基于 reV 构建风电场宏观选址系统的技术方案、算法原理、数据结构、运行流程与工程化实现方式。文档目标是为投标评审、技术澄清、系统设计和后续实施提供统一的技术依据。

本文档所述方案以 reV 作为核心计算引擎，以自研业务系统作为任务编排、数据治理、结果服务和可视化展示平台，形成“专业能源分析内核 + 行业业务平台”的总体技术路线。

## 2. reV 概述

### 2.1 平台定位

reV 是一套开源的地理空间技术经济分析工具，面向风电、光伏、地热、抽水蓄能等可再生能源场景，能够对大范围区域开展以下分析：

- 技术可开发潜力评估
- 发电量与容量因子计算
- 场址级平准化度电成本计算
- 供应曲线构建
- 输电接入成本叠加
- 代表性功率曲线提取

从工程角度看，reV 不是单一算法脚本，而是一条由多个模块组成的标准化计算流水线。其既支持 Python API 调用，也支持命令行管道运行，适合本地验证、集群批处理和云端并行计算。

### 2.2 核心能力

根据仓库中的 README、CLI 和示例配置，reV 具备以下能力：

- 支持从单站点到洲际尺度的空间分析
- 支持 5 分钟级到小时级时间分辨率
- 支持单年或多年分析
- 支持高分辨率排除层约束
- 支持供应曲线聚合与输电成本叠加
- 支持代表性出力曲线提取
- 支持 HPC 集群并行执行
- 支持风电场布局优化的 bespoke 模式

### 2.3 技术特点

reV 在风电宏观选址中的技术特点主要体现在以下方面：

1. 计算链路完整。可从风资源时序数据直接推导出场址容量因子、年发电量、站址 LCOE、输电成本和全口径供应曲线。
2. 数据模型统一。资源数据、排除层、项目点、输电表和输出成果均采用稳定的数据结构，便于工程落地。
3. 约束表达灵活。排除层支持按数值范围、枚举值、权重和连通区域阈值等方式组合约束。
4. 可扩展性强。可接入自定义成本乘子、区域属性、附加数据层、风机模板和微观布局优化模型。
5. 并行能力成熟。支持通过 pipeline 与批量任务运行在 HPC 平台，也支持小规模本地运行。

### 2.4 版本、许可与生态

根据仓库根目录的 `CITATION.cff`：

- 软件名称：reV
- 当前仓库标注版本：0.15.0
- 许可证：BSD-3-Clause
- 代码仓库：<https://github.com/NatLabRockies/reV>
- 软件 DOI：10.5281/zenodo.4501716

reV 的常用生态工具包括：

- rex：资源数据 I/O 与 HDF5 处理
- reVX：地理预处理、退让区和输电前处理
- reVRt：输电路径与成本计算
- NRWAL：海上风电、氢能等成本方程库
- reView：供应曲线交互可视化
- gaps：管道任务调度与管理

## 3. 面向投标项目的总体技术路线

### 3.1 系统边界划分

本方案不建议重复开发一个新的能源分析内核，而建议将 reV 作为风电宏观选址计算引擎，并在其外侧构建业务系统。职责划分如下：

- reV 负责资源发电模拟、空间排除分析、供应曲线聚合、输电成本叠加、代表性曲线提取、可选的风电场微观布局优化。
- 业务系统负责参数录入、方案管理、任务调度、日志监控、配置生成、成果入库、接口发布和地图展示。

### 3.2 推荐系统架构

建议采用五层架构：

1. 展示层：地图选区、约束条件配置、方案对比、任务监控、结果展示与导出。
2. 业务服务层：项目管理、场景管理、参数管理、风机模板管理、版本管理、权限与审计。
3. 配置生成层：将业务参数渲染为 `project_points.csv`、各类 `config_*.json`、排除规则和输出目录。
4. 执行层：调用 `reV pipeline` 或单模块 CLI，运行在本地、HPC 或云端批处理环境。
5. 结果服务层：解析 HDF5/CSV 输出，生成数据库摘要、专题图层、统计报表和 API 服务。

### 3.3 技术路线图

```text
风资源 HDF5 / 排除层 HDF5 / 项目点 CSV / SAM JSON / 输电表 CSV
                |
                v
        配置生成与任务装配
                |
                v
   reV generation -> collect -> multi-year
                |
                v
  supply-curve-aggregation -> supply-curve
                |
                +--> rep-profiles
                +--> qa-qc
                +--> bespoke(可选)
                |
                v
    结果入库 / 地图专题 / 报表导出 / API 服务
```

## 4. reV 如何实现风电场宏观选址

### 4.1 标准工作流程

reV 的标准计算流程通常由 7 个阶段组成：

1. `generation`
2. `collect`
3. `multi-year`
4. `supply-curve-aggregation`
5. `supply-curve`
6. `rep-profiles`
7. `qa-qc`

对于风电项目，还可在某些候选供应曲线点上增加 `bespoke` 布局优化，形成“宏观选址 + 微观排布”的两级分析体系。

### 4.2 典型 pipeline 配置

仓库示例 `examples/full_pipeline_execution/config_pipeline.json` 的结构如下：

```json
{
  "pipeline": [
    {"generation": "./config_gen.json"},
    {"collect": "./config_collect.json"},
    {"multi-year": "./config_multi-year.json"},
    {"supply-curve-aggregation": "./config_aggregation.json"},
    {"supply-curve": "./config_supply-curve.json"},
    {"rep-profiles": "./config_rep-profiles.json"},
    {"qa-qc": "./config_qa-qc.json"}
  ]
}
```

该结构表明 reV 通过配置文件驱动完整计算链路，业务系统只需要按项目场景生成标准配置，即可实现可重复、可审计、可重跑的自动化流程。

### 4.3 阶段一：Generation 发电仿真

#### 4.3.1 功能定位

`generation` 模块以风资源时序数据和 SAM 风机配置为输入，计算每个项目点在目标年份下的发电性能。核心实现入口是 `reV.generation.generation.Gen`。

#### 4.3.2 典型输入

仓库示例 `examples/batched_execution/config_gen.json`：

```json
{
  "analysis_years": [2010, 2011],
  "project_points": "./project_points/project_points.csv",
  "resource_file": "/datasets/WIND/conus/v1.0.0/wtk_conus_{}.h5",
  "sam_files": {
    "turbine": "./sam_configs/turbine.json"
  },
  "technology": "windpower",
  "output_request": ["cf_mean"]
}
```

#### 4.3.3 内部处理流程

`generation` 的核心处理流程可概括为以下步骤：

**步骤一：项目点解析**

读取 `project_points.csv`，获得待计算资源点 `gid` 列表及对应的 SAM 配置名称。每个 `gid` 映射到风资源 HDF5 中的一个空间网格点。

**步骤二：多高度风资源提取**

从 WTK HDF5 文件中，依据 SAM 配置中的 `wind_turbine_hub_ht`，提取对应高度层（或相邻高度层以备插值）的时间序列数据，包括风速（m/s）、风向（°）、气温（K 或 °C）及大气压（Pa）。数据维度为 `[time, site]`，时间步通常为小时级（8760 步/年）或更高分辨率（如 5 分钟级）。

**步骤三：风廓线高度外推**

若 WTK 中存储的标准高度与轮毂高度不完全一致，reV 通过 SAM 的内部幂律风廓线模型进行高度外推，外推使用 SAM 配置中的 `wind_resource_shear`（幂律剪切指数 $\alpha$）：

$$
v_h = v_{ref} \cdot \left(\frac{h}{h_{ref}}\right)^\alpha
$$

其中 $v_h$ 为轮毂高度 $h$ 处的风速，$v_{ref}$ 为参考高度 $h_{ref}$ 处的已知风速，$\alpha$ 为地表粗糙度相关的剪切指数（中性大气稳定度典型值约为 0.14–0.20）。

**步骤四：资源数据注入 SAM**

reV 将提取的时序数据按 SAM 规定格式组装：资源矩阵字段顺序为 `[temperature, pressure, windspeed, winddirection]`，高度字段统一设为轮毂高度。`wind_resource_model_choice = 0` 表示标准时序模式，SAM 直接读取该矩阵逐时驱动风机模型。

**步骤五：PySAM 风电模型仿真**

将完整 SAM 配置注入 `PySAM.Windpower` 模块并执行计算。SAM 在每个时间步执行以下核心计算：

- 根据气压和气温计算实际空气密度，并对功率曲线进行空气密度修正；
- 将校正后的风速映射到修正后的功率曲线，得到该时步机组输出；
- 若配置了多机位布局（`wind_farm_xCoordinates/yCoordinates`），还会执行尾流模型计算，对下游机位风速进行折减。

**步骤六：结果收集**

计算完毕后，将站点级时序及标量输出写入 HDF5 输出文件。分布式运行时，每个 worker 负责一批站点，由后续 `collect` 阶段合并。

#### 4.3.4 生成阶段关键输出

常见输出包括：

- `cf_mean`
- `cf_profile`
- `annual_energy`
- `lcoe_fcr`
- `system_capacity`

这些结果既可作为单站点分析结果，也可作为后续供应曲线聚合的输入基础。

### 4.4 阶段二：Collect 结果收集

在 HPC 环境下，`generation` 通常会将子任务分发到多个节点或 worker 上。`collect` 的作用是将分散输出进行合并，形成统一的中间结果文件，供后续模块继续使用。

该阶段本身算法复杂度不高，但在工程上非常关键，因为它承担了多节点结果归并、失败任务重试后合流、输出路径标准化等职责。

### 4.5 阶段三：Multi-year 多年聚合

当项目需要多年资源稳定性分析时，`multi-year` 用于对多年的 `cf_mean`、`lcoe_fcr` 等指标进行统计聚合。常见产物包括：

- 多年均值，例如 `cf_mean-means`
- 多年统计量，例如标准差等

多年分析使系统不仅可以回答“某一年是否适合建设”，还可以回答“多年平均是否稳定、极端年份表现如何、年际波动是否可接受”等项目决策问题。

### 4.6 阶段四：Supply-Curve-Aggregation 供应曲线聚合

#### 4.6.1 功能定位

这是风电宏观选址的核心阶段。它将高分辨率排除层、资源映射关系和发电指标聚合为供应曲线点，形成“适合建设的候选区域单元”。

关键类包括：

- `reV.supply_curve.points.AbstractSupplyCurvePoint`
- `reV.supply_curve.points.SupplyCurvePoint`
- `reV.supply_curve.sc_aggregation.SupplyCurveAggregation`

#### 4.6.2 示例配置

仓库示例 `examples/full_pipeline_execution/config_aggregation.json`：

```json
{
  "cf_dset": "cf_mean-means",
  "data_layers": {
    "reeds_region": {"dset": "reeds_regions", "method": "mode"},
    "slope": {"dset": "srtm_slope", "method": "mean"}
  },
  "excl_dict": {
    "smod": {"inclusion_weights": {"1": 0.5, "2": 1, "3": 1}},
    "srtm_slope": {"inclusion_range": [null, 5], "weight": 1.0}
  },
  "excl_fpath": "./rev_conus_exclusions.h5",
  "gen_fpath": "PIPELINE",
  "lcoe_dset": "lcoe_fcr-means",
  "power_density": 31.5,
  "resolution": 64,
  "tm_dset": "techmap_wtk"
}
```

风电项目中，`power_density` 应按风电技术参数进行配置，而不是直接套用光伏示例值。

#### 4.6.3 该阶段解决的问题

在实际风电选址中，资源网格通常较粗，而约束条件栅格通常较细。`supply-curve-aggregation` 通过高分辨率排除层把“理论上有风”的区域筛选成“工程上可开发”的区域，并进一步将这些区域聚合成可排序、可比较、可接入输电分析的供应曲线点。

### 4.7 阶段五：Supply-Curve 输电成本叠加与排序

#### 4.7.1 功能定位

该阶段将供应曲线点与外部输电设施关联，计算每个候选点接入输电系统的成本，并生成最终可排序的供应曲线。核心类是 `reV.supply_curve.supply_curve.SupplyCurve`。

#### 4.7.2 示例配置

仓库示例 `examples/full_pipeline_execution/config_supply-curve.json`：

```json
{
  "fixed_charge_rate": 0.096,
  "sc_points": "PIPELINE",
  "trans_table": "./conus_trans_lines_cache_064_sj_infsink.csv",
  "transmission_costs": {
    "available_capacity": 0.3,
    "center_tie_in_cost": 10,
    "line_cost": 1000,
    "line_tie_in_cost": 200,
    "sink_tie_in_cost": 100,
    "station_tie_in_cost": 50
  }
}
```

#### 4.7.3 该阶段输出的意义

仅知道“风资源好”并不足以指导投资，还必须知道“接入电网是否经济”。该阶段将站址 LCOE 与输电接入成本组合，形成真正可用于投资排序和开发优选的全口径成本指标。

### 4.8 阶段六：Rep-Profiles 代表性曲线提取

`rep-profiles` 从供应曲线点对应的基础发电时序中，提取可代表某区域或某资源等级的典型出力曲线。仓库示例 `examples/full_pipeline_execution/config_rep-profiles.json` 中给出了如下典型参数：

```json
{
  "analysis_years": [2011, 2012, 2013],
  "cf_dset": "cf_profile-{}",
  "err_method": "rmse",
  "n_profiles": 5,
  "reg_cols": ["reeds_region", "res_class"],
  "rep_method": "meanoid"
}
```

该阶段的结果可直接用于：

- 电网消纳仿真
- 典型日分析
- 多能源互补分析
- 储能配置研究
- 电力市场收益测算

### 4.9 阶段七：QA-QC 质量保证

`qa-qc` 用于检查输出完整性、统计异常、空间分布合理性和模块间结果一致性，保证最终交付成果可复核、可追溯、可解释。

### 4.10 可选阶段：Bespoke 风电场微观布局优化

`bespoke` 并非宏观选址必选步骤，但对入围候选区的精细化评估非常有价值。它可以在供应曲线点内部，依据可建设区域和最小机间距自动生成风机布局，并将布局结果再次反馈到能量与成本计算中。

仓库示例 `examples/bespoke_wind_plants/single_run.py` 展示了 `BespokeSinglePlant` 的单点运行方法，其核心输入包括：

- 排除层 HDF5
- 资源 HDF5
- Techmap 数据集
- SAM 系统输入
- 目标函数与成本函数
- 遗传算法参数

## 5. 输入数据与格式说明

### 5.1 风资源数据

风电分析以 HDF5 资源文件为基础，通常符合 rex 数据格式。典型数据集包括：

- `windspeed_{height}m`
- `winddirection_{height}m`
- `temperature_{height}m`
- `pressure_{height}m`
- `latitude`
- `longitude`
- `time_index`

典型结构如下：

```text
wtk_conus_2010.h5
├── /windspeed_100m          [time, site]
├── /winddirection_100m      [time, site]
├── /temperature_100m        [time, site]
├── /pressure_100m           [time, site]
├── /latitude                [site]
├── /longitude               [site]
└── /time_index              [time]
```

字段说明：

- 时间维通常为 8760 小时或更高分辨率时序
- 空间维是资源网格点编号 `gid`
- `gid` 是项目点与资源数据建立映射关系的核心主键

### 5.2 项目点文件 `project_points.csv`

这是 generation 阶段的基础输入。仓库中的风电示例文件格式如下：

```csv
gid,config
0,turbine
1,turbine
2,turbine
3,turbine
```

字段含义如下：

- `gid`：资源网格点编号
- `config`：绑定的 SAM 配置名称

在源码枚举 `SiteDataField` 中，标准列名包括：

- `gid`
- `config`
- `curtailment`

工程实施时，业务数据库可维护更完整的候选点对象，例如经纬度、地市县、地形分区、项目版本和风机模板版本，最终由配置生成层导出 reV 所需的最小 CSV。

### 5.3 SAM 风机配置 JSON

风电站模型的基础参数由 SAM JSON 给出。仓库示例 `examples/batched_execution/sam_configs/turbine.json` 包含如下核心字段：

**资源与模型控制**

- `wind_resource_model_choice`：资源输入模式。`0` 表示时序风资源文件模式（标准 WTK 模式）；`1` 表示韦伯分布模式（仅在无时序资源时使用）；`2` 表示风向-风速联合概率分布模式。reV 标准流程使用 `0`，由 `generation` 模块自动注入 WTK 时序数据。
- `weibull_k_factor`：韦伯分布形状参数（仅当 `wind_resource_model_choice = 1` 时生效）。
- `weibull_reference_height`：韦伯分布参考高度（m），同上，仅在分布模式下有意义。
- `weibull_wind_speed`：韦伯分布尺度参数/参考风速（m/s），同上。

**风轮与机组参数**

- `wind_turbine_hub_ht`：轮毂高度（m）。reV 使用该值确定从 WTK 提取哪个高度层的风速，并由 SAM 内部根据剪切指数插值到精确轮毂高度。
- `wind_turbine_powercurve_windspeeds`：风速-功率曲线的风速采样点（m/s），通常以 0.25 m/s 为步长。
- `wind_turbine_powercurve_powerout`：与上述风速对应的机组输出功率（kW），定义切入、额定、切出区间。
- `wind_turbine_max_cp`：最大风能利用系数 $C_{p,max}$，供 SAM 内部特性计算使用。
- `wind_turbine_rotor_diameter`：风轮直径（m），影响机间距约束和尾流计算。
- `wind_resource_shear`：风剪切指数 $\alpha$，用于幂律风廓线插值（典型值 0.14，对应中性大气稳定度）。
- `wind_resource_turbulence_coeff`：湍流强度系数，用于部分尾流模型（典型值 0.10）。

**风场参数**

- `system_capacity`：风场总装机容量（kW）。若未显式指定，SAM 会从功率曲线自动推断单台额定功率再乘机位数。
- `wind_farm_xCoordinates`：各机位相对坐标 X（m），与 Y 坐标共同定义机组阵列布局，用于尾流计算。
- `wind_farm_yCoordinates`：各机位相对坐标 Y（m）。
- `wind_farm_wake_model`：尾流模型选项。`0` = 无尾流损失；`1` = 简单尾流（Simple/Top-Hat 模型）；`2` = 园区尾流（Park/WAsP 模型）；`3` = 涡扩散模型（Eddy Viscosity）。bespoke 模式通常采用 `2`。
- `wind_farm_losses_percent`：综合系统损失率（%），涵盖集电线路、可用率、结冰等其他损失，作为额外折减施加于整场发电量。

**注意**：`wind_farm_losses_percent` 在新版 PySAM（>2.1.0）中已更名为 `turb_generic_loss`，reV 内部的 `PySAMVersionChecker` 会自动检测并映射该字段，业务系统无需单独处理。

### 5.4 排除层 HDF5

排除层是宏观选址的关键输入之一，用于表达不可建设区、低权重建设区和地理属性层。典型结构如下：

```text
rev_exclusions.h5
├── /srtm_slope
├── /land_use
├── /protected_areas
├── /distance_to_roads
├── /reeds_regions
├── /techmap_wtk
├── /latitude
└── /longitude
```

排除层的要求包括：

- 所有图层空间尺寸一致
- 具有一致的 CRS 与栅格配准关系
- 包含 `techmap_*` 数据集，用于把高分辨率排除像元映射到资源 `gid`

### 5.5 排除规则 `excl_dict`

`excl_dict` 用于定义每个图层的约束方式。典型形式如下：

```json
{
  "srtm_slope": {
    "inclusion_range": [null, 5],
    "weight": 1.0
  },
  "protected_areas": {
    "exclude_values": [1],
    "exclude_nodata": false
  },
  "smod": {
    "inclusion_weights": {
      "1": 0.5,
      "2": 1.0,
      "3": 1.0
    }
  }
}
```

可表达的规则包括：

- 枚举值排除
- 数值区间包含
- 按原始值作为权重
- 指定类别权重
- NoData 处理策略
- 最小连续区域面积约束

### 5.6 输电表 `trans_table`

`supply-curve` 模块依赖输电表。该表通常由外部输电路径工具生成，例如 reVX 的最小成本输电路径工具。其用途是给出每个供应曲线点与各输电接入设施之间的距离、可用容量和接入成本关系。

工程上应管理以下数据版本：

- 输电网络版本
- 变电站/负荷中心版本
- 接入成本假设版本
- 线路电压等级与容量版本

### 5.7 运行控制参数

reV 对大规模任务提供明确的执行控制参数，例如：

- `option`
- `nodes`
- `memory`
- `walltime`
- `allocation`
- `qos`
- `sites_per_worker`
- `max_workers`

这些参数决定了任务在本地、HPC 和云端环境中的执行方式。

## 6. 输出成果与数据结构

### 6.1 生成阶段输出

生成阶段常见输出字段包括：

- `cf_mean`
- `cf_profile`
- `annual_energy`
- `lcoe_fcr`
- `system_capacity`

其中 `cf_profile` 是后续代表性曲线提取的重要输入。

### 6.2 供应曲线标准输出字段

根据 `reV.utilities.SupplyCurveField` 枚举，供应曲线相关输出的标准字段包括：

- `sc_gid`
- `sc_point_gid`
- `sc_row_ind`
- `sc_col_ind`
- `latitude`
- `longitude`
- `res_gids`
- `gen_gids`
- `gid_counts`
- `capacity_factor_ac`
- `lcoe_site_usd_per_mwh`
- `capacity_ac_mw`
- `area_developable_sq_km`
- `annual_energy_site_mwh`
- `fixed_charge_rate`
- `losses_wakes_pct`

这些字段描述了候选供应曲线点的空间位置、资源映射关系、开发面积、容量、发电表现和站址级成本。

### 6.3 输电成本与全口径成本输出

输电相关关键字段包括：

- `trans_gid`
- `trans_type`
- `n_parallel_trans`
- `dist_spur_km`
- `reinforcement_dist_km`
- `trans_cap_cost_per_mw`
- `lcot_usd_per_mwh`
- `lcoe_all_in_usd_per_mwh`

在某些 CSV 或兼容输出中，也可能看到简化命名，例如：

- `lcot`
- `total_lcoe`

### 6.4 Bespoke 输出字段

微观布局优化相关字段包括：

- `possible_x_coords`
- `possible_y_coords`
- `turbine_x_coords`
- `turbine_y_coords`
- `n_turbines`
- `area_included_sq_km`
- `capacity_density_included_area_mw_per_km2`
- `area_convex_hull_sq_km`
- `capacity_density_convex_hull_mw_per_km2`

这些结果可用于风机排布图、集电线路估算和候选区精细化比选。

### 6.5 典型交付成果

本项目最终可形成以下交付成果：

1. 候选场址清单
2. 供应曲线排序表
3. 站址级容量因子与年发电量分析表
4. 站址级与全口径 LCOE 对比表
5. 排除层专题图与可开发面积图
6. 输电接入专题图
7. 代表性出力曲线集
8. 可选的微观风机布局方案图

## 7. 核心算法详解

### 7.1 排除层掩膜生成算法

排除层处理的目标，是把高分辨率空间栅格转换成可直接参与聚合计算的包含掩膜。对每一图层，系统按照 `excl_dict` 中的规则生成单层掩膜，然后对多层掩膜进行组合。

其基本形式可写为：

$$
M(x, y) = \prod_{k=1}^{n} m_k(x, y)
$$

其中：

- $M(x, y)$ 是最终包含掩膜
- $m_k(x, y)$ 是第 $k$ 个图层生成的掩膜或权重

若采用布尔掩膜，则 $m_k \in \{0,1\}$；若采用权重掩膜，则 $m_k \in [0,1]$。

典型处理流程如下：

```python
final_mask = 1
for layer_name, rule in excl_dict.items():
    layer = excl_h5[layer_name]
    layer_mask = build_mask(layer, rule)
    final_mask = final_mask * layer_mask
```

完成多层叠加后，还会对连通区域进行筛选。常见方式包括：

- `queen`：8 连通
- `rook`：4 连通

若某连续区域面积小于最小阈值 `min_area`，则该斑块被剔除。这样可避免输出一批虽然满足单点条件、但面积过小而无法实际建设的碎片区域。

### 7.2 供应曲线点网格划分与索引

`SupplyCurvePoint` 的核心思想，是把高分辨率排除层按照固定分辨率聚合为规则网格。默认分辨率常用 `resolution = 64`，即一个供应曲线点最多对应 $64 \times 64 = 4096$ 个高分辨率像元。

如果排除层尺寸为 $(H, W)$，则供应曲线列数为：

$$
n_{cols} = \left\lceil \frac{W}{resolution} \right\rceil
$$

对于任意供应曲线点编号 `gid`，其二维网格坐标为：

$$
row = gid // n_{cols}
$$

$$
col = gid \bmod n_{cols}
$$

源码中 `AbstractSupplyCurvePoint` 正是按该逻辑计算 `sc_row_ind` 和 `sc_col_ind`，并进一步解析该点在高分辨率排除层中的行列切片范围。

### 7.3 Techmap 资源映射与加权聚合

高分辨率排除像元与资源网格点并不一一对应，因此必须通过 `techmap_*` 数据集建立映射。对某个供应曲线点，先取其覆盖的排除像元，再从 `techmap` 中查出这些像元对应的资源 `gid`，形成该点的资源集合。

聚合变量 $x$ 的加权平均公式为：

$$
\bar{x} = \frac{\sum_{i=1}^{n} w_i x_i}{\sum_{i=1}^{n} w_i}
$$

其中：

- $x_i$ 为像元或资源点属性值
- $w_i$ 为包含权重

该公式适用于：

- 平均风速
- 平均容量因子
- 平均坡度
- 加权成本乘子

### 7.4 风向的圆统计聚合

风向不是线性变量，不能直接做普通平均。例如 $359^\circ$ 与 $1^\circ$ 的平均值不应是 $180^\circ$。因此 reV 对风向采用圆统计的矢量平均方法：

$$
\theta = \operatorname{atan2}\left(\sum_i w_i \sin\theta_i, \sum_i w_i \cos\theta_i\right)
$$

该方法可以正确反映风向分布的中心方向，是风电聚合分析中的必要处理。

### 7.5 发电模拟与功率曲线计算

风电 generation 阶段由 PySAM 的 `Windpower` 模块驱动，完整计算逻辑如下。

#### 7.5.1 风廓线高度外推

WTK 通常存储多个标准高度层（如 40 m、80 m、100 m、120 m、160 m、200 m）的风速。当轮毂高度与存储高度不完全对应时，SAM 内部采用**幂律风廓线**（Power Law Wind Profile）进行高度插值：

$$
v_h = v_{ref} \cdot \left(\frac{h}{h_{ref}}\right)^\alpha
$$

其中：

- $v_h$：目标高度 $h$（轮毂高度）处风速（m/s）
- $v_{ref}$：参考高度 $h_{ref}$ 处已知风速（m/s）
- $\alpha$：剪切指数（SAM 配置中 `wind_resource_shear`），典型范围 0.10–0.25，中性大气约为 0.14

对于温度和气压，SAM 也按对应的大气模型外推至轮毂高度，以用于空气密度修正。

#### 7.5.2 空气密度修正

标准功率曲线基于标准大气密度（$\rho_0 = 1.225$ kg/m³）建立。实际运行中，空气密度随海拔和温度变化，影响风轮捕获功率。SAM 将实际空气密度 $\rho$ 代入功率系数方程作等效风速修正：

$$
v_{eq} = v \cdot \left(\frac{\rho}{\rho_0}\right)^{1/3}
$$

等效风速 $v_{eq}$ 再映射回标准功率曲线，从而获得密度修正后的机组输出功率。

#### 7.5.3 功率曲线映射

功率曲线定义了风速到单台机组额定工况输出功率的映射关系 $P = f(v)$，分为三个工作区间：

| 区间 | 风速范围 | 特征 |
| --- | --- | --- |
| 切入前 | $v < v_{ci}$ | 风速不足，机组不发电，$P = 0$ |
| 工作区 | $v_{ci} \leq v \leq v_r$ | 功率随风速近似三次方增长，$P \propto v^3$ |
| 额定区 | $v_r < v \leq v_{co}$ | 机组限功率运行，$P = P_r$（额定功率） |
| 切出后 | $v > v_{co}$ | 安全保护停机，$P = 0$ |

$v_{ci}$、$v_r$、$v_{co}$ 分别为切入、额定和切出风速，从 `wind_turbine_powercurve_windspeeds` 和 `wind_turbine_powercurve_powerout` 字段中读出，SAM 对中间风速采用线性插值。

#### 7.5.4 尾流损失计算

当风场布局涉及多台机组（`wind_farm_xCoordinates/yCoordinates` 包含多个坐标）时，SAM 依据 `wind_farm_wake_model` 选项对下游机组进行尾流损失计算：

- **0（无尾流）**：不计尾流，每台机组均按自由来流风速运行，适用于机位间距极大或宏观快速估算。
- **1（简单尾流 / Top-Hat 模型）**：假设尾流为均匀速度亏损的圆锥形区域（线性扩展），每台机组叠加所有上游尾流影响，计算简单、速度快。
- **2（园区尾流 / Park / WAsP 模型）**：基于 Jensen（1983）尾流模型，尾流半径线性增长，速度亏损满足质量守恒。该模型在宏观选址和供应曲线分析中最为常用，reV 的 bespoke 优化模式也默认使用此模型：

$$
\frac{\Delta v}{v_0} = \left(1 - \sqrt{1 - C_T}\right) \cdot \left(\frac{r_0}{r_0 + k d}\right)^2
$$

其中 $C_T$ 为推力系数，$k$ 为尾流扩张系数（与湍流强度 `wind_resource_turbulence_coeff` 相关），$d$ 为机间距，$r_0$ 为风轮半径。

整场输出功率为所有机位功率之和：

$$
P_{total} = \sum_{j=1}^{N} f\left(v_j^{eff}\right)
$$

其中 $v_j^{eff}$ 为第 $j$ 台机组经尾流修正后的有效风速。

#### 7.5.5 综合损失折减

`wind_farm_losses_percent`（新版 PySAM 中为 `turb_generic_loss`）作为综合折减系数，对以上计算所得整场发电量作最终缩放，涵盖：

- 集电线路电气损失
- 机组可用率损失
- 低温/结冰期损失
- 控制与并网损失

### 7.6 年发电量与容量因子计算

对于给定电站：

$$
AEP = \sum_{t=1}^{T} P_t
$$

若按年小时数换算，则容量因子可写为：

$$
CF = \frac{AEP}{Capacity \times 8760}
$$

在供应曲线阶段，源码中标准字段名为 `capacity_factor_ac` 和 `annual_energy_site_mwh`。

### 7.7 场址级 LCOE 计算

源码 `reV.econ.utilities.lcoe_fcr` 明确给出了固定费率法（Fixed Charge Rate Method）LCOE 公式：

$$
LCOE = \left(\frac{FCR \times CAPEX + FOC}{AEP} + VOC\right) \times 1000
$$

各参数的**单位定义**如下（严格遵守 `reV/econ/utilities.py` 中的注释）：

| 参数 | 含义 | 单位 |
| --- | --- | --- |
| $FCR$ | 固定费率（资本回收率） | 无量纲，如 0.096 |
| $CAPEX$ | 总资本性支出 | \$ |
| $FOC$ | 年固定运维成本 | \$/年 |
| $AEP$ | 年发电量 | kWh |
| $VOC$ | 可变运维成本 | \$/kWh |

公式中 `(FCR × CAPEX + FOC) / AEP` 的中间结果单位为 `$/kWh`，加上 `VOC`（`$/kWh`）后，乘以 1000 将整体结果从 `$/kWh` 换算为 `$/MWh`，即最终输出的 LCOE 单位为 **\$/MWh**。

**关于 AEP 的计算方式**：在供应曲线聚合阶段，若启用 LCOE 重算（`recalc_lcoe = True`），AEP 由以下表达式推导：

$$
AEP = Capacity_{kW} \times CF \times 8760
$$

其中 $Capacity_{kW}$ 来自 SAM 配置的 `system_capacity`（kW），$CF$ 为多年均值容量因子（`cf_mean-means`）。用多年均值 CF 重算 LCOE 可避免单年异常导致系统性偏差，这也是实际项目中推荐启用该选项的原因。

供应曲线聚合后的标准输出字段为：

- `lcoe_site_usd_per_mwh`（供应曲线点加权平均 LCOE）
- `mean_lcoe`（源码内部中间量，供 `SupplyCurve` 阶段读取）

### 7.8 输电成本 LCOT 计算

源码 `reV.supply_curve.supply_curve.SupplyCurve.compute_total_lcoe` 中，LCOT 的核心实现为：

$$
LCOT = \frac{Cost_{trans,MW} \times FCR}{CF \times 8760}
$$

其中：

- $Cost_{trans,MW}$：单位 MW 的输电资本成本
- $FCR$：固定费率
- $CF$：场址平均容量因子

若存在强化改造成本，系统会将强化成本先加到单位 MW 输电成本中，再计算 LCOT。

对应源码中的全口径 LCOE 公式为：

$$
LCOE_{all-in} = LCOE_{site} + LCOT
$$

标准输出字段为：

- `lcot_usd_per_mwh`
- `lcoe_all_in_usd_per_mwh`

### 7.9 供应曲线排序与输电竞争

`SupplyCurve` 支持竞争式和非竞争式两类接入逻辑：

#### 非竞争式（Non-Competitive）

每个供应曲线点独立选择全口径 LCOE（`lcoe_all_in_usd_per_mwh`）最低的输电接入方案，不考虑其他点是否已占用同一输电设施的容量。输出结果按全口径 LCOE 升序排列，形成理论最优供应曲线。此模式适合初步筛选和资源潜力评估。

#### 竞争式（Competitive）

系统以全口径 LCOE 为排序键，从优到劣逐一处理供应曲线点：

1. 对当前候选点，在满足可用容量约束的输电设施中选择接入成本最低的方案；
2. 将该方案占用的容量从对应输电设施的剩余容量中扣除；
3. 对后续候选点，仅允许接入剩余容量大于其装机规模的输电设施。

这种贪心策略模拟了真实世界中先接入者优先占用输电资源（PPA 和并网协议）的竞争格局，通常导致靠后排序的候选点只能接入更远或更高成本的输电方案，全口径 LCOE 因此上升，最终供应曲线斜率随开发规模增大而逐渐抬升——这也是"供应曲线"这一术语的经济学含义所在。

`available_capacity` 参数（`transmission_costs` 中的键）控制输电设施可被外部接入的容量比例，用于预留冗余或表达已有接入协议。

### 7.10 Bespoke 布局优化算法

`bespoke` 模块采用三阶段优化路径，将排除层约束与风资源时序仿真深度耦合，直接在供应曲线点分辨率上完成机位布局与经济性评估的联合优化。

#### 第一阶段：可建设区域多边形化

对包含掩膜中的每个有效像元构造矩形多边形，并通过 Shapely 的 `unary_union` 操作将像元合并为一个或多个连通的可建设区域多边形。随后以**最小机间距的一半**对多边形内边界做缓冲退让（Minkowski 侵蚀），生成 `packing_polygons`——即实际允许放置风机轮毂的有效区域，确保边界处的机组与排除区的安全距离满足约束。

#### 第二阶段：候选风机位置生成

系统在 `packing_polygons` 内部采用**六边形紧密堆积**方式生成满足最小机间距约束的候选点集合，模拟蜂窝式最密排列。若候选点数量超过优化算法可高效处理的上限，系统以迭代方式逐步加大点间距，直到候选数量收敛到可优化规模（通常几十到几百个候选位）。

#### 第三阶段：差分进化优化

系统以**二进制布局向量** $\mathbf{b} \in \{0,1\}^N$ 作为决策变量，表示 $N$ 个候选位是否实际安装风机：

$$
\mathbf{b} = [b_1, b_2, \ldots, b_N], \quad b_i \in \{0, 1\}
$$

每个候选布局方案 $\mathbf{b}$ 对应一次完整的 PySAM 风场仿真和成本评估，计算目标函数值（适应度）。reV 内部默认调用 **scipy 差分进化（Differential Evolution）** 求解器驱动优化：

- **目标函数**：用户通过字符串表达式在配置中定义，由系统在每次仿真后求值。仓库测试中的真实示例：

```python
objective_function = (
    "(0.0975 * capital_cost + fixed_operating_cost) / aep "
    "+ variable_operating_cost"
)
```

  其结构即 LCOE 的简化形式，也可替换为 AEP 最大化、单位面积能量密度最大化等任意可计算表达式。

- **成本函数**：资本成本和固定运维成本可表示为装机容量的函数，实现规模经济效应建模：

```python
capital_cost_function = (
    "140 * system_capacity "
    "* exp(-system_capacity / 1e5 * 0.1 + (1 - 0.1))"
)
```

- **约束处理**：机间距约束已通过第一/第二阶段的几何操作隐式保证，优化阶段无需额外罚函数。

**优化收敛**：最大迭代代数和种群规模可通过配置控制；当目标函数改善低于设定阈值时提前终止，返回目标函数值最优的布局向量及对应完整仿真结果。

### 7.11 代表性曲线提取算法

`rep-profiles` 在各（区域、资源等级）组合下，从属于该组的所有供应曲线点对应时序发电曲线中，选出 $n$ 条最具代表性的曲线。示例配置采用 `rep_method = "meanoid"`、`err_method = "rmse"`。

#### Meanoid 算法流程

1. **均值曲线计算**：对组内全部时序计算逐时均值，得到"组均值曲线" $\bar{\mathbf{p}}$。
2. **误差度量**：以 `err_method`（通常为 RMSE）衡量各候选时序与均值曲线的相似度：

$$
RMSE_i = \sqrt{\frac{1}{T} \sum_{t=1}^{T} (p_{i,t} - \bar{p}_t)^2}
$$

3. **代表曲线选取**：选择 RMSE 最小的 $n$ 条时序曲线（`n_profiles` 参数控制），使得选出的曲线在整体形态上最接近组内真实均值水平。

**Meanoid 与 Medoid 的区别**：Medoid 从数据集中选出与其他所有样本平均距离最小的实际样本；Meanoid 以虚拟均值曲线作为参考目标，因此选出的曲线在对均值曲线的均方误差意义上更优，但不等于 Medoid 选出的中位数曲线。两者均保留了真实时间序列形态，优于人工合成"平均日"曲线。

`reg_cols` 参数（如 `["reeds_region", "res_class"]`）定义分组维度，不同区域和资源等级的代表曲线独立提取，支持分区电网消纳建模。代表曲线的典型下游用途包括：

- 短期/季节性电力平衡分析（电网消纳仿真）
- 多能互补系统协同优化
- 电力市场收益测算与合同谈判支持
- 储能配置容量研究

## 8. 关键数据结构说明

### 8.1 `SupplyCurvePoint`

`SupplyCurvePoint` 是供应曲线聚合的核心对象之一。其关键信息包括：

- `gid`：供应曲线点编号
- `resolution`：聚合分辨率
- `rows` / `cols`：在高分辨率排除层中的切片范围
- `sc_row_ind` / `sc_col_ind`：供应曲线网格行列号
- `res_gids`：映射到该点的资源点编号集合
- `gid_counts`：各资源点被包含的像元数
- `inclusion_mask`：包含权重掩膜

该对象起到了“空间高分辨率像元”和“资源/发电低分辨率网格”之间的桥梁作用。

### 8.2 供应曲线字段枚举

`reV.utilities.SupplyCurveField` 统一定义了供应曲线输出字段的标准名称。其价值在于：

- 降低不同模块之间的字段歧义
- 保证 CSV、DataFrame、HDF5 输出的一致性
- 为结果服务层提供稳定接口契约

### 8.3 配置文件数据模型

reV 的所有模块均由 JSON 配置驱动。典型配置对象由以下几类键构成：

- 输入路径键：如 `resource_file`、`project_points`、`excl_fpath`
- 算法参数键：如 `resolution`、`power_density`、`fixed_charge_rate`
- 执行控制键：如 `nodes`、`memory`、`walltime`
- 输出选择键：如 `output_request`、`cf_dset`、`lcoe_dset`

这种结构非常适合与企业级参数管理系统结合，因为业务系统可以持久化参数对象，再由渲染器输出标准配置文件。

## 9. 工程实现细节与部署方案

### 9.1 运行方式建议

对于投标项目的软件建设，建议优先采用 CLI 方式执行标准流程，而不是将所有算法直接嵌入 Web 服务线程中。推荐原因如下：

1. 配置和执行解耦，便于审计与复现。
2. 可与异步任务系统天然对接。
3. 更适合 HPC 和批量调度。
4. 出错后可按模块重跑，不必整链路回滚。

推荐命令示例如下：

```bash
reV pipeline -c ./config_pipeline.json
```

```bash
reV generation -c ./config_gen.json
```

### 9.2 本地与集群环境

根据仓库 README，推荐安装方式为：

```bash
conda create --name rev python=3.11
conda activate rev
pip install NLR-reV
```

若需要 HSDS 支持，可使用：

```bash
pip install NLR-reV[hsds]
```

README 中给出的典型运行规模为：

- WTK CONUS：每个年份约 10 至 20 个节点，壁钟时间约 1 至 4 小时
- NSRDB CONUS：约 5 个节点，壁钟时间约 2 小时

这说明 reV 既适合区域级开发项目，也适合省级、全国级、多年份方案比选。

### 9.3 建议的软件实现要点

为保证项目建设质量，建议在业务系统中补齐以下能力：

1. 风资源数据集管理
2. 风机模板库管理
3. 排除规则模板管理
4. 输电网络版本管理
5. 任务编排与日志追踪
6. HDF5 输出解析与数据库摘要生成
7. 结果地图切片与专题展示
8. 方案对比分析与导出

### 9.4 推荐的最小可用产品范围

若按分阶段实施，建议最小可用系统先交付以下能力：

1. 项目区范围选择与参数录入
2. `project_points.csv` 自动生成
3. `generation + collect + multi-year + supply-curve-aggregation + supply-curve` 全链路自动运行
4. 候选点排序表与地图展示
5. 报表导出

在第二阶段再扩展：

1. `rep-profiles`
2. `qa-qc`
3. `bespoke` 微观布局优化
4. 多方案并行比选与成本情景分析

## 10. 本方案的技术优势

### 10.1 面向宏观选址的专业性

本方案直接采用 reV 已成熟的风资源发电分析与供应曲线技术路线，而不是用简单 GIS 叠图替代物理和经济计算，因此结果更具工程可用性。

### 10.2 面向投资决策的完整性

本方案不仅输出风资源优良区，还输出：

- 可开发面积
- 可装机容量
- 年发电量
- 场址级 LCOE
- 输电接入成本
- 全口径 LCOE

这使其可直接用于投资排序和前期决策。

### 10.3 面向工程实施的可扩展性

本方案支持：

- 新排除图层接入
- 新风机机型接入
- 成本参数本地化
- 集群与云端部署
- 与现有 GIS 平台、项目管理平台和数据中台集成

### 10.4 面向交付的可审计性

由于全流程由配置文件驱动，输入、参数、版本和输出均可留痕，因此项目交付过程具备良好的可审计性和复现性。

## 11. 参考资料来源

本文档的技术说明基于以下资料编制：

### 11.1 当前代码仓库中的文档、代码和示例

- 根目录 `README.rst`
- 根目录 `CITATION.cff`
- `reV/generation/generation.py`
- `reV/supply_curve/points.py`
- `reV/supply_curve/supply_curve.py`
- `reV/econ/utilities.py`
- `reV/utilities/__i__nit__.__py`
- `examples/batched_execution/`
- `examples/full_pipeline_execution/`
- `examples/bespoke_wind_plants/single_run.py`
- 根目录现有技术草稿 `tender.md`

### 11.2 官方网站与在线文档

- GitHub 仓库：<https://github.com/NatLabRockies/reV>
- 官方文档：<https://natlabrockies.github.io/reV/>
- CLI 文档：<https://natlabrockies.github.io/reV/_cli/cli.html>
- reV Python API 文档：<https://natlabrockies.github.io/reV/_autosummary/reV.html>

### 11.3 论文与技术报告

- `73067.pdf`
- README 中引用的 reV technical report：<https://www.nrel.gov/docs/fy19osti/73067.pdf>

### 11.4 其他在线资源

- reVX：<https://natlabrockies.github.io/reVX/>
- rex：<https://natlabrockies.github.io/rex/>
- reVRt：<https://natlabrockies.github.io/reVRt/>
- NRWAL：<https://natlabrockies.github.io/NRWAL/>
- gaps：<https://natlabrockies.github.io/gaps/>
- reView：<https://github.com/NatLabRockies/reView>

## 12. 结论

综上，reV 通过“风资源发电仿真 + 空间排除聚合 + 输电成本叠加 + 代表性曲线提取 + 可选微观布局优化”的技术体系，实现了风电场宏观选址从资源评价到投资排序的全流程闭环。

对于本投标项目，采用 reV 作为选址计算引擎具有以下现实意义：

- 能够快速建立标准化、可复用、可审计的风电宏观选址平台
- 能够在省域、区域乃至全国尺度开展多方案比选
- 能够以统一数据模型支撑 GIS 可视化、报表输出和后续项目开发
- 能够在后续阶段自然扩展到微观布局优化、储能协同分析和电网消纳分析

因此，本方案技术路线成熟、实现路径清晰、工程可操作性强，适合作为风电场宏观选址系统建设的核心技术方案。