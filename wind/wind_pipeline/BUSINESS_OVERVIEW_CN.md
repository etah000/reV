# 本地风电 Pipeline 业务说明

本文档从业务视角说明本示例中每个关键数据文件的作用，以及每个
pipeline 步骤分别在解决什么问题。

## 适用范围

这是一个基于 Rhode Island 测试数据的本地风电 pipeline 示例，核心
目标是回答一个实际业务问题：

哪些可开发风电区域可以形成可连接的供给曲线点，这些点在接入电网
后的成本排序是什么。

## 数据文件说明

### 核心输入数据

- ../../tests/data/wtk/ri_100_wtk_2012.h5
  - 业务角色：风资源事实来源。
  - 它提供每个资源 gid 的风资源和天气信号，用于估算风电项目发电
    表现。
  - 在本示例中，它同时用于 generation 计算和 techmap 构建。

- ../../tests/data/ri_exclusions/ri_exclusions.h5
  - 业务角色：选址约束层。
  - 它定义了哪些区域可以开发、哪些区域因保护、限制或不可建设等原
    因被排除。

- ../../tests/data/trans_tables/ri_transmission_table.csv
  - 业务角色：电网接入候选清单。
  - 它提供候选输电设施及距离信息，使供给曲线点可以进行接入和按交
    付成本排序。

- ../../tests/data/SAM/wind_gen_standard_losses_0.json
  - 业务角色：风机与项目性能假设集。
  - 它定义 reV 通过 SAM 使用的关键参数，如装机容量、损失假设等。

- ./project_points.csv
  - 业务角色：待评估站点组合定义。
  - 它告诉 reV 要模拟哪些资源 gid。
  - 当前文件包含 RI 资源文件前 100 个 gid，以保证 aggregation 阶段
    能形成非空的 supply-curve 点。

### 工作和派生数据

- ./ri_exclusions_local.h5
  - 业务角色：本示例可写的 exclusions 工作副本。
  - 它是仓库 exclusions 测试夹具的复制品，用来避免直接修改共享测
    试数据。
  - 相比原始 exclusions 文件，它只额外增加一个数据集：
    techmap_wtk_ri_100_local。

- ./local_wind_pipeline_ri_final_generation_2012.h5
  - 业务角色：站点级性能结果集。
  - 它保存选定 gid 的 generation 输出，例如 cf_mean 和下游需要的成
    本字段。

- ./local_wind_pipeline_ri_final_supply-curve-aggregation.csv
  - 业务角色：可开发区域聚合结果层。
  - 它把站点级模拟结果转换成供给曲线点，包括聚合后的容量、面积和
    平均表现指标。

- ./local_wind_pipeline_ri_final_supply-curve.csv
  - 业务角色：最终可接网开发排序结果。
  - 它把聚合后的供给曲线点与输电选项合并，形成最终可连接的供给曲
    线表。

## 配置文件说明

- ./config_pipeline.json
  - 总控编排文件，定义执行顺序。

- ./config_generation.json
  - generation 阶段的站点模拟配置。

- ./config_sc_aggregation.json
  - 空间聚合配置，用于把 exclusions、techmap 和 generation 输出整
    合成供给曲线点。

- ./config_supply_curve.json
  - 最终接网和成本排序配置。

## Pipeline 步骤说明

### 1. generation

业务含义：

- 把原始风资源信号转换成每个候选站点的发电表现。
- 这一阶段回答的问题是：如果在每个 gid 建设风电项目，基础发电和成
  本表现会是什么。

主要输入：

- 资源文件
- project points 文件
- SAM 参数假设

主要输出：

- local_wind_pipeline_ri_final_generation_2012.h5

### 2. supply-curve-aggregation

业务含义：

- 把站点级结果转换成反映土地可开发性和空间聚类后的供给曲线点。
- 这一阶段回答的问题是：在排除层生效后，哪些可开发区域存在，这些
  区域对应的聚合容量和平均表现是什么。

主要输入：

- generation 输出
- 本地 exclusions 文件
- 用于 techmap 生成的资源文件

主要输出：

- local_wind_pipeline_ri_final_supply-curve-aggregation.csv

### 3. supply-curve

业务含义：

- 将聚合后的供给曲线点连接到输电候选，并生成最终的交付成本排序。
- 这一阶段回答的问题是：哪些可开发点可以接网，它们接网后的成本顺
  序如何。

主要输入：

- supply-curve aggregation 输出
- transmission table

主要输出：

- local_wind_pipeline_ri_final_supply-curve.csv

## 为什么不包含 collect 和 multi-year

- collect 在这里不是必需的，因为 generation 已经直接生成了一个完
  整的单年输出文件，后续步骤可以直接使用。

- multi-year 在这里不是必需的，因为本示例目标是保持小体量、本地可
  跑、并围绕单个已验证资源年份构建稳定示例。

## 最新验证说明

- 该 pipeline 已于 2026-05-02 从零完整重跑通过。
- generation、supply-curve-aggregation、supply-curve 三步全部成功。
- supply-curve 步骤有 11 个点缺少 transmission 映射的非阻塞告警。
  这些点保持未连接状态，对本地示例是可接受的。