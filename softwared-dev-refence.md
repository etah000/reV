# 风电场宏观选址系统后端设计文档

**文档编号**：REV-BACKEND-DESIGN-001  
**版本**：v1.0  
**设计级别**：介于概要设计与详细设计之间（含接口签名，不含完整代码实现）  
**适用对象**：后端开发工程师、架构评审人员  
**关联文档**：`rev风电场宏观选址投标书技术说明.md`（算法原理背景）

---

## 目录

1. [文档说明](#1-文档说明)
2. [系统边界与职责划分](#2-系统边界与职责划分)
3. [总体架构](#3-总体架构)
4. [数据模型设计](#4-数据模型设计)
5. [模块设计](#5-模块设计)
6. [API 接口设计](#6-api-接口设计)
7. [配置生成器详细设计](#7-配置生成器详细设计)
8. [任务执行与状态管理](#8-任务执行与状态管理)
9. [结果解析规范](#9-结果解析规范)
10. [输入验证规范](#10-输入验证规范)
11. [部署与运行环境](#11-部署与运行环境)
12. [分阶段实施路径](#12-分阶段实施路径)

---

## 1. 文档说明

### 1.1 目标与读者

本文档描述以 **reV 0.15.0** 为计算引擎的风电场宏观选址系统**后端原型**的工程设计。阅读本文档的前提是已了解 reV 各计算模块的功能语义（参见关联文档《投标书技术说明》）。

本文不重复算法原理，而专注于：
- 系统如何与 reV 集成（边界划分）
- 数据应以何种结构持久化
- 各业务逻辑模块的接口规约
- reV 配置文件如何从数据库参数动态生成
- 任务生命周期如何被追踪和管理

### 1.2 设计层次定义

| 层次 | 含义 | 本文对应 |
|---|---|---|
| 概要设计 | 系统分层、模块划分、技术选型 | 第 2、3 节 |
| 详细设计 | 类/方法签名、字段表、接口规约、状态机 | 第 4–10 节 |
| 实现级 | 具体代码、SQL DDL、完整 OpenAPI YAML | **不在本文范围** |

### 1.3 范围声明

**本文覆盖**：
- 后端 REST API 服务（FastAPI）
- 异步任务调度（Celery + Redis）
- 数据持久化（PostgreSQL + PostGIS）
- reV 配置生成与 subprocess 封装
- 结果数据解析与入库
- 对象存储接口（MinIO）

**本文不覆盖**：
- 前端 / 地图可视化
- HPC 集群运维与 SLURM 脚本
- reV 算法内部实现
- 安全认证体系（OAuth2 / JWT 可插拔，不在原型范围）

---

## 2. 系统边界与职责划分

### 2.1 职责矩阵

| 能力项 | reV 负责 | 业务系统负责 |
|---|:---:|:---:|
| 数值天气预报数据读取（NSRDB/WTK HDF5） | ✓ | |
| SAM 模型调用（发电量计算） | ✓ | |
| 尾流损耗、计划性损耗建模 | ✓ | |
| 排除区域栅格叠加（H5 exclusions） | ✓ | |
| 供应曲线聚合与竞争性排序 | ✓ | |
| 技术图谱（techmap）生成 | ✓ | |
| 代表性曲线聚类 | ✓ | |
| config_*.json 文件构造 | | ✓ |
| project_points.csv 构造 | | ✓ |
| 场景参数管理（用户输入到配置的映射） | | ✓ |
| 任务状态追踪与日志回收 | | ✓ |
| 结果 HDF5/CSV 解析入库 | | ✓ |
| REST API 暴露 | | ✓ |
| 风机参数库管理 | | ✓ |
| 排除层元数据管理 | | ✓ |
| 输电网络版本管理 | | ✓ |
| 用户 / 权限管理 | | ✓（可选）|
| 前端地图可视化 | | ✓（不在本文）|

### 2.2 集成方式

业务系统以**进程外调用**方式使用 reV：

```
业务系统 → 生成 config_*.json + project_points.csv
         → subprocess 调用 `reV pipeline -c config_pipeline.json`
         → 轮询目录，收集输出 HDF5 / CSV
         → 解析结果写入 PostgreSQL
```

reV 不以 Python 库直接 import 拆分调用；这样可以：
1. 保持 reV 版本与业务系统解耦
2. 利用 Celery worker 进行进程级隔离
3. 直接复用 reV CLI 的日志和错误处理

### 2.3 四条设计原则

1. **配置即合约**：业务系统向 reV 传递的唯一接口是合法的配置 JSON 文件；严禁 monkey-patch reV 内部类。
2. **幂等任务**：同一 Job 可以重试；重试前清除上次的工作目录或使用带版本号的子目录。
3. **异步优先**：所有执行超时不可预知的操作（reV pipeline）必须放在 Celery worker 中，不得阻塞 HTTP 请求。
4. **Schema-first 数据**：所有从 HDF5/CSV 解析的结果字段在入库前必须通过 Pydantic 模型验证。

---

## 3. 总体架构

### 3.1 五层架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 1 – API 接入层                                 │
│  FastAPI  (uvicorn)   ← HTTP/REST                    │
│  Pydantic v2 Request/Response Schema                 │
└────────────────────┬────────────────────────────────┘
                     │ 调用
┌────────────────────▼────────────────────────────────┐
│  Layer 2 – 业务逻辑层                                 │
│  ScenarioService  ConfigGeneratorService             │
│  JobRunnerService  ResultParserService               │
│  DatasetService   TurbineTemplateService             │
│  ExclusionService  ResultQueryService                │
└──────────┬─────────────────────┬────────────────────┘
           │ 入队                 │ 读写
┌──────────▼──────────┐  ┌───────▼────────────────────┐
│  Layer 3 – 任务层    │  │  Layer 4 – 持久化层          │
│  Celery workers      │  │  PostgreSQL + PostGIS        │
│  Redis (broker)      │  │  （场景/任务/结果元数据）      │
│  subprocess → reV    │  │  MinIO（HDF5/CSV 原始文件）   │
└──────────┬──────────┘  └────────────────────────────┘
           │ 读写 HDF5/CSV
┌──────────▼──────────────────────────────────────────┐
│  Layer 5 – 计算层                                     │
│  reV 0.15.0 (Generation / SupplyCurve / RepProfiles) │
│  NREL-PySAM  /  SAM compute engine                   │
│  WTK HDF5 资源文件（本地或 HSDS 服务）                 │
└─────────────────────────────────────────────────────┘
```

### 3.2 技术选型

| 组件 | 选型 | 版本约束 | 选型理由 |
|---|---|---|---|
| Web框架 | FastAPI | ≥0.110 | 原生异步、Pydantic v2、自动 OpenAPI 文档 |
| 异步任务 | Celery | ≥5.3 | 成熟的 Python 任务队列，支持任务链、重试、ETA |
| 消息代理 | Redis | ≥7.0 | 轻量，同时作为 Celery broker 和结果后端 |
| 关系数据库 | PostgreSQL | ≥15 | PostGIS 支持空间查询；JSONB 存储 SAM 参数 |
| 空间扩展 | PostGIS | ≥3.4 | 供应曲线点的空间索引与邻近查询 |
| 对象存储 | MinIO | latest | S3 兼容接口，存储 HDF5/CSV 原始结果 |
| ORM | SQLAlchemy | ≥2.0 | async ORM，支持 PostGIS 类型 |
| 数据验证 | Pydantic | v2 | reV 结果字段白名单验证 |
| 配置文件 | Python stdlib `json` | — | reV 始终使用 JSON 配置，不使用 YAML |

### 3.3 一次完整请求链路

```
① 用户 POST /jobs {scenario_id}
          ↓
② FastAPI JobRunnerService.submit(scenario_id)
   → 创建 Job 记录（status=PENDING）
   → 构造工作目录 jobs/{job_id}/
   → ConfigGeneratorService.generate_all(job_id)
     ├─ 从 DB 加载 Scenario + TurbineTemplate + ExclusionRules
     ├─ 写 project_points.csv
     ├─ 写 config_gen.json, config_econ.json
     ├─ 写 config_sa.json, config_sc.json, config_rp.json
     └─ 写 config_pipeline.json
   → 将 Celery task `run_pipeline.delay(job_id)` 入队
   → 返回 {job_id, status="QUEUED"}
          ↓
③ Celery worker run_pipeline(job_id)
   → 更新 Job status=RUNNING
   → subprocess: `reV pipeline -c config_pipeline.json`
   → 实时 tail 日志，回填 JobStep 记录
   → 执行成功 → 触发 parse_results.delay(job_id)
   → 执行失败 → 更新 status=FAILED, error_msg
          ↓
④ Celery worker parse_results(job_id)
   → ResultParserService.parse(job_id)
     ├─ 读取 _sc.csv（供应曲线表）
     ├─ 验证字段（Pydantic ScPointSchema）
     ├─ 批量 upsert ScPoint 记录
     ├─ 读取 _rep_profiles.h5
     └─ 上传 profiles 至 MinIO，写 RepProfile 记录
   → 更新 Job status=SUCCESS
          ↓
⑤ 用户 GET /jobs/{id}/supply-curve
   → ResultQueryService.query_sc_points(job_id, filters, page)
   → 返回分页 GeoJSON
```
---

## 4. 数据模型设计

本节定义系统核心实体及其字段，关系描述以文字为主（不含 SQL DDL）。

### 4.1 Dataset（风资源数据集）

描述一份可供分析使用的气候/风资源数据集（WTK HDF5 文件集合）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `dataset_id` | UUID PK | 主键 |
| `name` | VARCHAR(128) | 用户命名，如 "WTK-CONUS-2012" |
| `technology` | ENUM | `windpower` / `pvwattsv8` |
| `path_pattern` | TEXT | HDF5 文件路径模式，如 `/data/wtk/{year}.h5` |
| `analysis_years` | INT[] | 可用年份列表，如 `[2012, 2013, 2014]` |
| `extent_wkt` | TEXT | 空间范围（WKT POLYGON） |
| `crs` | VARCHAR(32) | 坐标系，如 `EPSG:4326` |
| `resolution_m` | FLOAT | 格网分辨率（米） |
| `status` | ENUM | `active` / `retired` |
| `created_at` | TIMESTAMPTZ | 创建时间 |

**关系**：被 `Scenario` 引用（多 Scenario 可指向同一 Dataset）。

---

### 4.2 TurbineTemplate（风机模板）

描述一种风机型号的完整 SAM-compatible 参数集合。

| 字段 | 类型 | 说明 |
|---|---|---|
| `template_id` | UUID PK | 主键 |
| `name` | VARCHAR(128) | 如 "GE-2.8-127" |
| `version` | VARCHAR(32) | 版本标签 |
| `system_capacity_kw` | FLOAT | 单机装机容量（kW） |
| `hub_height_m` | FLOAT | 轮毂高度（m） |
| `rotor_diameter_m` | FLOAT | 风轮直径（m） |
| `power_curve_json` | JSONB | `{"wind_turbine_powercurve_windspeeds": [...], "wind_turbine_powercurve_powerout": [...]}` |
| `wake_model` | SMALLINT | 0=无，1=简单尾流（Jensen），2=扩展尾流 |
| `shear_exponent` | FLOAT | 风切变指数 α（默认 0.14） |
| `turbulence_coeff` | FLOAT | 湍流强度系数 |
| `losses_pct` | FLOAT | 系统总损耗（%），含 `wind_farm_losses_percent` |
| `sam_json` | JSONB | 完整渲染后的 SAM 配置（由 ConfigGenerator 生成，写配置时填充） |
| `created_at` | TIMESTAMPTZ | 创建时间 |

**关系**：被 `Scenario` 引用。

---

### 4.3 ExclusionLayer（排除图层）

描述一个物理排除图层（对应 reV exclusions HDF5 文件中的一个 dataset）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `layer_id` | UUID PK | 主键 |
| `name` | VARCHAR(128) | 如 "slope_pct"、"protected_areas" |
| `dataset_name` | VARCHAR(256) | HDF5 文件中 dataset 的路径键 |
| `h5_fpath` | TEXT | exclusions HDF5 文件的绝对路径 |
| `description` | TEXT | 图层说明 |
| `version` | VARCHAR(32) | 版本标签 |

---

### 4.4 ExclusionRule（排除规则）

描述一条应用于某图层的具体排除/权重规则，对应 `reV.supply_curve.exclusions` 的参数。

| 字段 | 类型 | 说明 |
|---|---|---|
| `rule_id` | UUID PK | 主键 |
| `layer_id` | UUID FK → ExclusionLayer | 关联图层 |
| `scenario_id` | UUID FK → Scenario | 规则属于哪个场景 |
| `rule_type` | ENUM | `range` / `values` / `weights` |
| `inclusion_range_min` | FLOAT NULL | 仅 rule_type=range 时有效 |
| `inclusion_range_max` | FLOAT NULL | 仅 rule_type=range 时有效 |
| `exclude_values` | FLOAT[] NULL | 仅 rule_type=values 时有效 |
| `inclusion_weights` | JSONB NULL | 仅 rule_type=weights 时有效，格式 `{value: weight, ...}` |
| `exclude_nodata` | BOOL | 是否排除 nodata 像元 |
| `weight` | FLOAT | 加权系数（0–1），默认 1.0 |
| `min_area_km2` | FLOAT NULL | 最小连通区域面积过滤 |

**关系**：多条规则属于同一 Scenario；一条规则绑定一个 ExclusionLayer。

---

### 4.5 TransmissionNetwork（输电网络版本）

| 字段 | 类型 | 说明 |
|---|---|---|
| `network_id` | UUID PK | 主键 |
| `name` | VARCHAR(128) | 如 "CONUS-2023-Q1" |
| `version` | VARCHAR(32) | 版本标签 |
| `trans_table_fpath` | TEXT | 输电线路表 CSV 绝对路径 |
| `region` | VARCHAR(64) | 地理区域 |
| `voltage_kv` | INT NULL | 主要电压等级 |
| `notes` | TEXT | 备注 |

---

### 4.6 Scenario（分析场景）

一次完整的宏观选址分析参数集合，是创建 Job 的模板。

| 字段 | 类型 | 说明 |
|---|---|---|
| `scenario_id` | UUID PK | 主键 |
| `name` | VARCHAR(256) | 用户命名 |
| `dataset_id` | UUID FK → Dataset | 所用风资源数据集 |
| `turbine_template_id` | UUID FK → TurbineTemplate | 所用风机模板 |
| `transmission_network_id` | UUID FK → TransmissionNetwork | 所用输电网络版本 |
| `analysis_years` | INT[] | 分析年份（必须是 Dataset.analysis_years 的子集） |
| `power_density_mw_km2` | FLOAT | 装机密度 (MW/km²)，用于 supply-curve 计算 |
| `resolution` | INT | SC 聚合分辨率（像元数），如 64 |
| `fixed_charge_rate` | FLOAT | 固定电荷率，用于 LCOE 计算，如 0.096 |
| `output_request` | VARCHAR[] | Generation 输出字段列表，如 `["cf_mean", "annual_energy"]` |
| `econ_enabled` | BOOL | 是否运行 econ 模块（单次所有者 LCOE）|
| `rep_profiles_enabled` | BOOL | 是否运行代表性曲线提取 |
| `created_by` | VARCHAR(128) NULL | 创建者 |
| `created_at` | TIMESTAMPTZ | 创建时间 |

**关系**：一个 Scenario 可以启动多个 Job（如重跑、参数微调）。

---

### 4.7 Job（任务）

一次 reV pipeline 的执行实例。

| 字段 | 类型 | 说明 |
|---|---|---|
| `job_id` | UUID PK | 主键 |
| `scenario_id` | UUID FK → Scenario | 来源场景 |
| `status` | ENUM | `PENDING` / `QUEUED` / `RUNNING` / `SUCCESS` / `FAILED` / `RETRYING` |
| `work_dir` | TEXT | 任务工作目录绝对路径 |
| `celery_task_id` | VARCHAR(64) NULL | Celery task ID |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `started_at` | TIMESTAMPTZ NULL | 实际开始时间 |
| `finished_at` | TIMESTAMPTZ NULL | 完成时间 |
| `error_msg` | TEXT NULL | 失败时的错误摘要 |
| `retry_count` | SMALLINT | 重试次数，默认 0 |

---

### 4.8 JobStep（任务步骤）

Job 中每个 reV pipeline 步骤的执行记录。

| 字段 | 类型 | 说明 |
|---|---|---|
| `step_id` | UUID PK | 主键 |
| `job_id` | UUID FK → Job | 所属任务 |
| `step_name` | VARCHAR(64) | 如 `generation`, `collect`, `supply-curve` |
| `step_order` | SMALLINT | 步骤序号 |
| `status` | ENUM | `PENDING` / `RUNNING` / `SUCCESS` / `FAILED` |
| `started_at` | TIMESTAMPTZ NULL | 开始时间 |
| `finished_at` | TIMESTAMPTZ NULL | 完成时间 |
| `exit_code` | SMALLINT NULL | subprocess 退出码 |
| `log_path` | TEXT NULL | 日志文件路径 |

---

### 4.9 ScPoint（供应曲线点）

supply-curve CSV 解析后的结构化结果，每行对应一个 SC 格网点。

| 字段 | 类型 | 说明 |
|---|---|---|
| `sc_point_id` | BIGSERIAL PK | 主键 |
| `job_id` | UUID FK → Job | 来源任务 |
| `sc_gid` | INT | reV 原始 sc_point_gid |
| `latitude` | DOUBLE PRECISION | 纬度 |
| `longitude` | DOUBLE PRECISION | 经度 |
| `capacity_ac_mw` | FLOAT | 可开发装机容量（MW） |
| `capacity_factor_ac` | FLOAT | 年平均容量因子 |
| `annual_energy_mwh` | FLOAT | 年发电量（MWh） |
| `lcoe_site_usd_per_mwh` | FLOAT | 场址 LCOE（$/MWh），不含输电 |
| `lcot_usd_per_mwh` | FLOAT | 输电成本（$/MWh） |
| `lcoe_all_in_usd_per_mwh` | FLOAT | 全成本 LCOE（$/MWh） |
| `area_developable_sq_km` | FLOAT | 可开发面积（km²） |
| `trans_gid` | INT NULL | 接入输电线 gid |
| `trans_type` | VARCHAR(32) NULL | 接入点类型 |
| `dist_spur_km` | FLOAT NULL | 支线距离（km） |
| `geometry` | GEOMETRY(Point, 4326) | PostGIS 空间列，用于空间查询 |

---

### 4.10 RepProfile（代表性曲线）

| 字段 | 类型 | 说明 |
|---|---|---|
| `profile_id` | UUID PK | 主键 |
| `job_id` | UUID FK → Job | 来源任务 |
| `region_key` | VARCHAR(128) | 区域标识，如行政区划编码 |
| `res_class` | SMALLINT | 资源等级（1–10） |
| `profile_index` | INT | 在 rep-profiles HDF5 中的索引 |
| `storage_url` | TEXT | MinIO 对象路径，如 `s3://results/job_id/profiles.h5` |
| `year_range` | INT4RANGE | 覆盖年份范围 |
| `n_timesteps` | INT | 时间步数（通常 8760） |

---

## 5. 模块设计

本节定义各业务逻辑服务类的职责边界和主要方法签名（含参数名和类型，不包含实现代码）。所有 Service 类通过依赖注入获取数据库 Session 和配置对象。

---

### 5.1 DatasetService

**职责**：管理风资源数据集元数据的 CRUD，并校验 HDF5 文件路径可达性。

```python
class DatasetService:
    def __init__(self, db: AsyncSession): ...

    async def create(self, payload: DatasetCreateSchema) -> Dataset: ...
    async def get(self, dataset_id: UUID) -> Dataset: ...
    async def list(self, technology: str | None = None) -> list[Dataset]: ...
    async def validate_paths(self, dataset_id: UUID, years: list[int]) -> list[str]:
        """返回无法访问的 HDF5 路径列表（空列表表示全部可达）"""
```

---

### 5.2 TurbineTemplateService

**职责**：管理风机模板的 CRUD，并提供将模板参数序列化为 reV SAM 配置字典的功能。

```python
class TurbineTemplateService:
    def __init__(self, db: AsyncSession): ...

    async def create(self, payload: TurbineTemplateCreateSchema) -> TurbineTemplate: ...
    async def get(self, template_id: UUID) -> TurbineTemplate: ...
    async def list(self) -> list[TurbineTemplate]: ...
    def render_sam_config(self, template: TurbineTemplate) -> dict:
        """将 TurbineTemplate 字段映射为 SAM windpower 配置字典"""
    async def validate_power_curve(self, template_id: UUID) -> list[str]:
        """校验功率曲线单调性和合理范围，返回问题描述列表"""
```

---

### 5.3 ExclusionService

**职责**：管理排除图层元数据和规则，并将规则序列化为 reV exclusions 配置格式。

```python
class ExclusionService:
    def __init__(self, db: AsyncSession): ...

    async def create_layer(self, payload: ExclusionLayerCreateSchema) -> ExclusionLayer: ...
    async def list_layers(self) -> list[ExclusionLayer]: ...
    async def add_rule(self, scenario_id: UUID, payload: ExclusionRuleCreateSchema) -> ExclusionRule: ...
    async def get_rules_for_scenario(self, scenario_id: UUID) -> list[ExclusionRule]: ...
    def render_exclusion_config(self, rules: list[ExclusionRule]) -> dict:
        """
        将规则列表转为 reV ExclusionMaskCombined 初始化参数字典：
        {layer_name: {"inclusion_range": [min, max], "weight": w, ...}, ...}
        """
```

---

### 5.4 ScenarioService

**职责**：管理场景 CRUD，并在创建/更新时校验外键完整性和参数合理性。

```python
class ScenarioService:
    def __init__(self, db: AsyncSession,
                 dataset_svc: DatasetService,
                 turbine_svc: TurbineTemplateService): ...

    async def create(self, payload: ScenarioCreateSchema) -> Scenario: ...
    async def get(self, scenario_id: UUID) -> Scenario: ...
    async def update(self, scenario_id: UUID, payload: ScenarioUpdateSchema) -> Scenario: ...
    async def list(self, page: int = 1, page_size: int = 20) -> list[Scenario]: ...
    async def validate(self, scenario_id: UUID) -> list[str]:
        """
        前置校验：
        - analysis_years 是否在 Dataset.analysis_years 内
        - 功率曲线是否有效
        - HDF5 文件是否可达
        - trans_table_fpath 是否存在
        返回问题描述列表（空列表表示通过）
        """
```

---

### 5.5 ConfigGeneratorService

**职责**：从数据库读取 Scenario 及关联实体，生成一套完整的 reV 配置文件到指定工作目录。这是系统中最核心的模块，详细设计见第 7 节。

```python
class ConfigGeneratorService:
    def __init__(self, db: AsyncSession,
                 exclusion_svc: ExclusionService,
                 turbine_svc: TurbineTemplateService): ...

    async def generate_all(self, job_id: UUID) -> Path:
        """
        生成完整配置套件，返回工作目录 Path。
        生成文件：project_points.csv, config_gen.json,
                   config_econ.json, config_sa.json,
                   config_sc.json, config_rp.json,
                   config_pipeline.json
        """
    async def render_project_points(
            self, scenario: Scenario, candidates: list[dict]) -> Path:
        """生成 project_points.csv，返回文件路径"""
    async def render_config_gen(self, scenario: Scenario, job_dir: Path) -> Path:
        """生成 config_gen.json，返回文件路径"""
    async def render_config_sc(self, scenario: Scenario, job_dir: Path) -> Path:
        """生成 config_sc.json（供应曲线），返回文件路径"""
    async def render_config_pipeline(
            self, scenario: Scenario, job_dir: Path, steps: list[str]) -> Path:
        """生成 config_pipeline.json，含 PIPELINE 占位符解析"""
    def _resolve_pipeline_output(self, step_name: str, job_dir: Path) -> str:
        """解析上一步骤的输出路径，填入 PIPELINE 字段"""
```

---

### 5.6 JobRunnerService

**职责**：创建 Job 记录，调用 ConfigGeneratorService 准备配置，提交 Celery 任务。

```python
class JobRunnerService:
    def __init__(self, db: AsyncSession,
                 config_gen: ConfigGeneratorService,
                 celery_app: Celery): ...

    async def submit(self, scenario_id: UUID) -> Job:
        """
        1. 创建 Job(status=PENDING)
        2. 创建 JobStep 记录（每步 PENDING）
        3. 调用 config_gen.generate_all(job_id)
        4. 入队 celery run_pipeline task
        5. 更新 Job(status=QUEUED, celery_task_id=...)
        6. 返回 Job
        """
    async def cancel(self, job_id: UUID) -> Job:
        """撤销 Celery 任务，更新 Job status=CANCELLED"""
    async def retry(self, job_id: UUID) -> Job:
        """清除失败状态，重新入队（递增 retry_count）"""
```

---

### 5.7 JobStatusService

**职责**：提供任务状态查询和步骤日志读取接口，被 API 层轮询使用。

```python
class JobStatusService:
    def __init__(self, db: AsyncSession): ...

    async def get_job(self, job_id: UUID) -> Job: ...
    async def list_steps(self, job_id: UUID) -> list[JobStep]: ...
    async def update_step_status(
            self, step_id: UUID, status: str,
            exit_code: int | None = None) -> JobStep: ...
    async def read_log_tail(self, job_id: UUID, step_name: str,
                            lines: int = 100) -> str:
        """读取指定步骤日志文件末尾 N 行"""
```

---

### 5.8 ResultParserService

**职责**：读取 reV 输出文件（CSV/HDF5），验证字段，批量入库。

```python
class ResultParserService:
    def __init__(self, db: AsyncSession, storage: MinIOClient): ...

    async def parse(self, job_id: UUID) -> None:
        """
        1. 定位 _sc.csv 和 _profiles.h5
        2. parse_supply_curve(job_id, sc_csv_path)
        3. parse_rep_profiles(job_id, profiles_h5_path) if enabled
        4. 更新 Job status=SUCCESS
        """
    async def parse_supply_curve(
            self, job_id: UUID, sc_csv_path: Path) -> int:
        """解析 CSV，Pydantic 验证，批量 upsert ScPoint，返回入库行数"""
    async def parse_rep_profiles(
            self, job_id: UUID, profiles_h5_path: Path) -> int:
        """上传 HDF5 至 MinIO，写 RepProfile 元数据记录，返回记录数"""
    def _validate_sc_row(self, row: dict) -> ScPointSchema:
        """对单行数据执行 Pydantic v2 验证，抛出 ValidationError 终止解析"""
```

---

### 5.9 ResultQueryService

**职责**：提供供应曲线查询、分页和导出能力，直接暴露给 API 层。

```python
class ResultQueryService:
    def __init__(self, db: AsyncSession, storage: MinIOClient): ...

    async def query_sc_points(
            self, job_id: UUID,
            min_cf: float | None = None,
            max_lcoe: float | None = None,
            bbox: tuple[float, float, float, float] | None = None,
            page: int = 1,
            page_size: int = 500) -> tuple[list[ScPoint], int]:
        """返回 (记录列表, 总数)，支持容量因子/LCOE/空间 bbox 过滤"""
    async def export_csv(self, job_id: UUID) -> AsyncIterator[bytes]:
        """流式导出供应曲线 CSV（用于大数据量下载）"""
    async def get_summary(self, job_id: UUID) -> dict:
        """
        返回统计摘要：
        {total_capacity_mw, mean_cf, mean_lcoe,
         p10_lcoe, p50_lcoe, p90_lcoe, n_points}
        """
    async def get_rep_profile_url(
            self, job_id: UUID, region_key: str,
            res_class: int) -> str:
        """生成 MinIO presigned URL 供前端下载"""
```

---


## 6. API 接口设计

所有接口遵循 REST 惯例，使用 JSON 通信，HTTP 状态码表达结果。分页参数为 `?page=1&page_size=50`。

---

### 6.1 数据资产接口

#### Dataset

| Method | Path | 说明 |
|---|---|---|
| GET | `/datasets` | 列出所有数据集，可选 `?technology=windpower` 过滤 |
| POST | `/datasets` | 创建新数据集 |
| GET | `/datasets/{id}` | 获取单条数据集 |
| DELETE | `/datasets/{id}` | 软删除（将 status 设为 retired） |

**POST /datasets 请求体（关键字段）**：
```json
{
  "name": "WTK-CONUS-2012-2014",
  "technology": "windpower",
  "path_pattern": "/data/wtk/wtk_conus_{year}.h5",
  "analysis_years": [2012, 2013, 2014],
  "crs": "EPSG:4326",
  "resolution_m": 2000.0
}
```

#### TurbineTemplate

| Method | Path | 说明 |
|---|---|---|
| GET | `/turbine-templates` | 列出所有风机模板 |
| POST | `/turbine-templates` | 创建新模板 |
| GET | `/turbine-templates/{id}` | 获取单条模板 |
| PUT | `/turbine-templates/{id}` | 更新模板 |
| POST | `/turbine-templates/{id}/validate` | 校验功率曲线，返回 `{"valid": true, "issues": []}` |

**POST /turbine-templates 请求体（关键字段）**：
```json
{
  "name": "GE-2.8-127",
  "system_capacity_kw": 2800.0,
  "hub_height_m": 90.0,
  "rotor_diameter_m": 127.0,
  "power_curve_json": {
    "wind_turbine_powercurve_windspeeds": [0,1,2,3,4,5,6,7,8,9,10,11,12,25],
    "wind_turbine_powercurve_powerout":   [0,0,0,60,180,420,780,1230,1780,2350,2700,2800,2800,0]
  },
  "wake_model": 1,
  "shear_exponent": 0.14,
  "losses_pct": 15.0
}
```

#### ExclusionLayer

| Method | Path | 说明 |
|---|---|---|
| GET | `/exclusion-layers` | 列出所有排除图层 |
| POST | `/exclusion-layers` | 注册新排除图层 |
| GET | `/exclusion-layers/{id}` | 获取图层元数据 |

#### TransmissionNetwork

| Method | Path | 说明 |
|---|---|---|
| GET | `/transmission-networks` | 列出所有输电网络版本 |
| POST | `/transmission-networks` | 注册新版本 |
| GET | `/transmission-networks/{id}` | 获取详情 |

---

### 6.2 场景接口

| Method | Path | 说明 |
|---|---|---|
| GET | `/scenarios` | 分页列出场景 |
| POST | `/scenarios` | 创建新场景（含排除规则列表） |
| GET | `/scenarios/{id}` | 获取场景详情 |
| PUT | `/scenarios/{id}` | 更新场景参数 |
| POST | `/scenarios/{id}/validate` | 前置校验，返回 `{"valid": bool, "issues": [str]}` |

**POST /scenarios 请求体**：
```json
{
  "name": "华北平原 2012-2014 基准场景",
  "dataset_id": "...",
  "turbine_template_id": "...",
  "transmission_network_id": "...",
  "analysis_years": [2012, 2013, 2014],
  "power_density_mw_km2": 3.0,
  "resolution": 64,
  "fixed_charge_rate": 0.096,
  "output_request": ["cf_mean", "cf_profile", "annual_energy"],
  "econ_enabled": true,
  "rep_profiles_enabled": true,
  "exclusion_rules": [
    {"layer_name": "slope_pct", "rule_type": "range",
     "inclusion_range_min": 0, "inclusion_range_max": 15, "weight": 1.0},
    {"layer_name": "protected_areas", "rule_type": "values",
     "exclude_values": [1], "weight": 1.0}
  ]
}
```

---

### 6.3 任务接口

| Method | Path | 说明 |
|---|---|---|
| POST | `/jobs` | 提交新任务，body: `{"scenario_id": "..."}` |
| GET | `/jobs` | 分页列出任务，`?scenario_id=...&status=...` |
| GET | `/jobs/{id}` | 获取任务状态和元数据 |
| POST | `/jobs/{id}/cancel` | 取消排队或运行中的任务 |
| POST | `/jobs/{id}/retry` | 重试失败任务 |
| GET | `/jobs/{id}/steps` | 列出所有步骤状态 |
| GET | `/jobs/{id}/steps/{step_name}/log` | 获取步骤日志尾部，`?lines=200` |

**GET /jobs/{id} 响应体**：
```json
{
  "job_id": "...",
  "status": "RUNNING",
  "steps": [
    {"step_name": "generation", "status": "SUCCESS"},
    {"step_name": "collect", "status": "SUCCESS"},
    {"step_name": "supply-curve-aggregation", "status": "RUNNING"},
    {"step_name": "supply-curve", "status": "PENDING"},
    {"step_name": "rep-profiles", "status": "PENDING"}
  ],
  "started_at": "2024-01-15T09:00:00Z",
  "finished_at": null,
  "error_msg": null
}
```

---

### 6.4 结果接口

| Method | Path | 说明 |
|---|---|---|
| GET | `/jobs/{id}/summary` | 统计摘要（总装机、平均 CF、P50 LCOE 等） |
| GET | `/jobs/{id}/supply-curve` | 分页 GeoJSON，支持过滤参数 |
| GET | `/jobs/{id}/supply-curve/export` | 流式下载完整 CSV |
| GET | `/jobs/{id}/profiles` | 列出 RepProfile 元数据 |
| GET | `/jobs/{id}/profiles/{pid}/url` | 获取 MinIO presigned URL（有效期 1h） |

**GET /jobs/{id}/supply-curve 查询参数**：`min_cf`, `max_lcoe`, `bbox`（min_lon,min_lat,max_lon,max_lat）, `page`, `page_size`

**GET /jobs/{id}/summary 响应体**：
```json
{
  "job_id": "...",
  "n_points": 12847,
  "total_capacity_mw": 384210.5,
  "mean_cf": 0.312,
  "p10_lcoe": 28.3,
  "p50_lcoe": 37.1,
  "p90_lcoe": 52.4
}
```

---


## 7. 配置生成器详细设计

ConfigGeneratorService 是系统与 reV 之间的核心桥梁。本节详细描述每个生成目标文件的内容结构和字段映射规则。

---

### 7.1 任务目录结构

每个 Job 在文件系统上独占一个目录，结构如下：

```
/data/jobs/{job_id}/
├── inputs/
│   └── project_points.csv          # 候选点列表
├── configs/
│   ├── config_gen.json             # Generation 配置
│   ├── config_econ.json            # Econ 配置（可选）
│   ├── config_sa.json              # Supply-curve aggregation 配置
│   ├── config_sc.json              # Supply-curve 配置
│   ├── config_rp.json              # Rep-profiles 配置（可选）
│   └── config_pipeline.json        # Pipeline 总控配置
├── outputs/
│   ├── gen/                        # generation 输出（HDF5 per year）
│   ├── collect/                    # collect 输出（multi-year HDF5）
│   ├── sc_agg/                     # supply-curve-aggregation 输出
│   ├── sc/                         # supply-curve 输出（_sc.csv）
│   └── rp/                         # rep-profiles 输出（_profiles.h5）
└── logs/
    ├── generation_2012.log
    ├── collect.log
    ├── supply_curve_agg.log
    ├── supply_curve.log
    └── rep_profiles.log
```

---

### 7.2 project_points.csv 生成规则

project_points.csv 定义 Generation 计算的候选格网点集合。

**文件格式**：

```csv
gid,latitude,longitude,hub_height
0,39.52,-116.45,90
1,39.54,-116.43,90
...
```

**生成算法**：

1. 从 `Scenario.dataset_id` 获取 HDF5 文件，读取元数据中的坐标格网（`latitude`/`longitude` 数组）。
2. 可选：仅选取落在 `Scenario` 关联区域 Polygon 内的点（空间过滤）。
3. 可选：应用粗粒度排除掩膜预筛（仅写入非全排除点，减小计算量）。
4. `gid` 字段使用 reV 格网的原始 `gid`（即资源文件中的像元序号）。
5. `hub_height` 字段从 `TurbineTemplate.hub_height_m` 取值。
6. 写出 CSV 到 `{job_dir}/inputs/project_points.csv`。

**关于 `gid` 的重要说明**：reV generation 要求 `gid` 列与 HDF5 资源文件中的时序维度索引完全对应，不可自行重编号。

---

### 7.3 config_gen.json 字段映射

```json
{
  "technology": "windpower",
  "project_points": "PIPELINE",
  "sam_files": {
    "windpower": "{job_dir}/configs/sam_windpower.json"
  },
  "resource_file": "{dataset.path_pattern}",
  "output_request": ["cf_mean", "cf_profile", "annual_energy"],
  "log_directory": "{job_dir}/logs",
  "execution_control": {
    "option": "local",
    "max_workers": 4
  },
  "log_level": "INFO",
  "analysis_years": [2012, 2013, 2014]
}
```

| config_gen 字段 | 数据来源 | 说明 |
|---|---|---|
| `technology` | 固定值 `"windpower"` | |
| `project_points` | `"PIPELINE"` 占位，前一步输出 | 由 pipeline 解析注入 |
| `sam_files.windpower` | 生成的 sam_windpower.json 路径 | 见 7.4 节 |
| `resource_file` | `Dataset.path_pattern`，`{year}` 占位 | reV 自动按年展开 |
| `output_request` | `Scenario.output_request` | |
| `analysis_years` | `Scenario.analysis_years` | |
| `execution_control.max_workers` | 系统配置或默认 4 | |

---

### 7.4 sam_windpower.json 字段映射

SAM 风电配置由 `TurbineTemplateService.render_sam_config()` 生成：

| SAM 字段 | TurbineTemplate 字段 | 说明 |
|---|---|---|
| `system_capacity` | `system_capacity_kw` | 单机容量（kW） |
| `wind_turbine_hub_ht` | `hub_height_m` | 轮毂高度（m） |
| `wind_turbine_rotor_diameter` | `rotor_diameter_m` | 风轮直径（m） |
| `wind_turbine_powercurve_windspeeds` | `power_curve_json.wind_turbine_powercurve_windspeeds` | 功率曲线风速序列 |
| `wind_turbine_powercurve_powerout` | `power_curve_json.wind_turbine_powercurve_powerout` | 功率曲线出力序列（kW） |
| `wind_farm_wake_model` | `wake_model` | 尾流模型类型（0/1/2） |
| `wind_resource_shear` | `shear_exponent` | 风剖面切变指数 α |
| `wind_farm_losses_percent` | `losses_pct` | 风场综合损耗百分比 |
| `turb_generic_loss` | 默认 `0` | 独立湍流损耗，已并入 losses_pct |

---

### 7.5 config_sa.json（supply-curve-aggregation）字段映射

```json
{
  "project_points": "PIPELINE",
  "gen_fpath": "PIPELINE",
  "tm_dset": "techmap_wtk",
  "excl_fpath": "{exclusion_h5_path}",
  "excl_dict": { ... },
  "res_class_dset": "winddirection_100m",
  "cf_dset": "cf_mean",
  "lcoe_dset": "lcoe_fcr",
  "data_layers": {},
  "resolution": 64,
  "power_density": 3.0,
  "log_directory": "{job_dir}/logs"
}
```

| config_sa 字段 | 数据来源 | 说明 |
|---|---|---|
| `gen_fpath` | `"PIPELINE"` | collect 步骤输出的多年 HDF5 路径 |
| `tm_dset` | 固定 `"techmap_wtk"` | WTK 技术图谱 dataset 名称 |
| `excl_fpath` | `ExclusionLayer.h5_fpath`（所有规则同文件） | |
| `excl_dict` | `ExclusionService.render_exclusion_config()` 输出 | 规则列表 → 字典 |
| `resolution` | `Scenario.resolution` | 聚合分辨率（像元数） |
| `power_density` | `Scenario.power_density_mw_km2` | 装机密度（MW/km²） |

**excl_dict 生成示例**（来自 ExclusionService.render_exclusion_config）：
```json
{
  "slope_pct": {
    "inclusion_range": [0, 15],
    "weight": 1.0,
    "exclude_nodata": true
  },
  "protected_areas": {
    "exclude_values": [1],
    "weight": 1.0
  }
}
```

---

### 7.6 config_sc.json（supply-curve）字段映射

```json
{
  "sc_points": "PIPELINE",
  "trans_table": "{transmission_network.trans_table_fpath}",
  "fixed_charge_rate": 0.096,
  "sc_features": "PIPELINE",
  "transmission_costs": {"line_tie_in_cost": 14000, "line_cost": 3667},
  "log_directory": "{job_dir}/logs"
}
```

| config_sc 字段 | 数据来源 | 说明 |
|---|---|---|
| `sc_points` | `"PIPELINE"` | supply-curve-aggregation 输出的聚合点 CSV |
| `trans_table` | `TransmissionNetwork.trans_table_fpath` | 输电线路表路径 |
| `fixed_charge_rate` | `Scenario.fixed_charge_rate` | 固定电荷率（用于 LCOT 计算） |
| `transmission_costs` | 系统默认值（可在 Scenario 中扩展） | 单位成本（$/MW·km 等） |

---

### 7.7 config_pipeline.json 与 PIPELINE 占位符解析

config_pipeline.json 控制各步骤的执行顺序和上下游数据传递。

**PIPELINE 字段说明**：在对应 config 中将输入路径设置为字符串 `"PIPELINE"` 时，reV pipeline 会自动将上一步骤的输出文件路径注入该字段。

**config_pipeline.json 结构**：
```json
{
  "pipeline": [
    {"generation": "{job_dir}/configs/config_gen.json"},
    {"collect": "{job_dir}/configs/config_collect.json"},
    {"supply-curve-aggregation": "{job_dir}/configs/config_sa.json"},
    {"supply-curve": "{job_dir}/configs/config_sc.json"},
    {"rep-profiles": "{job_dir}/configs/config_rp.json"}
  ],
  "logging": {"log_level": "INFO"}
}
```

**步骤启用逻辑**：
- 如果 `Scenario.econ_enabled=True`，在 generation 后插入 `econ` 步骤。
- 如果 `Scenario.rep_profiles_enabled=False`，从 pipeline 列表中去除 `rep-profiles`。
- `collect` 步骤：当 `len(analysis_years) > 1` 时启用，单年数据直接跳过。

---

### 7.8 生成文件的顺序约束

ConfigGeneratorService.generate_all() 内部的生成顺序：

```
1. 确保工作目录结构存在（mkdir -p）
2. render_sam_config() → sam_windpower.json
3. render_project_points() → inputs/project_points.csv
4. render_config_gen() → configs/config_gen.json
5. render_config_collect() → configs/config_collect.json（如多年）
6. render_config_econ() → configs/config_econ.json（如 econ_enabled）
7. render_config_sa() → configs/config_sa.json
8. render_config_sc() → configs/config_sc.json
9. render_config_rp() → configs/config_rp.json（如 rep_profiles_enabled）
10. render_config_pipeline() → configs/config_pipeline.json
```

生成期间任何步骤失败都应抛出异常，由 JobRunnerService 捕获并将 Job status 设为 FAILED。

---


## 8. 任务执行与状态管理

### 8.1 任务状态机

```
         +----------------------------------------------------------+
         |                                                          |
  [创建] -> PENDING -> QUEUED -> RUNNING -> SUCCESS                 |
                                    |                              |
                                    v                              |
                                  FAILED -> RETRYING  ------------->+
                                    |
                                  CANCELLED（终态，不可重试）
```

**状态转换说明**：

| 状态 | 触发条件 |
|---|---|
| PENDING | Job 记录刚创建，ConfigGenerator 未运行或运行中 |
| QUEUED | ConfigGenerator 完成，Celery task 已入队 |
| RUNNING | Celery worker 开始执行 `reV pipeline` subprocess |
| SUCCESS | subprocess 退出码 0，ResultParser 完成入库 |
| FAILED | subprocess 非零退出码，或 ResultParser 异常 |
| RETRYING | 用户触发重试，retry_count 递增，重新进入 QUEUED |
| CANCELLED | 用户取消，Celery revoke + 记录终态 |

**步骤状态独立追踪**：每个 `JobStep` 拥有独立的状态字段，Celery worker 通过轮询日志文件中 reV pipeline 的步骤完成标记来驱动 JobStep 状态更新。

---

### 8.2 Celery 任务链设计

系统使用两个 Celery 任务，通过 `chain()` 串联：

```python
from celery import chain

pipeline = chain(
    run_pipeline.s(job_id),
    parse_results.s(job_id)
)
pipeline.apply_async()
```

**run_pipeline(job_id)**：
1. 更新 Job status → RUNNING
2. 启动 subprocess：`reV pipeline -c {job_dir}/configs/config_pipeline.json`
3. 实时 tail stdout/stderr，匹配步骤完成标记，更新 JobStep 状态
4. subprocess 退出后检查退出码：
   - 0 → 继续 chain（触发 parse_results）
   - 非零 → 更新 Job status=FAILED, error_msg，中断 chain

**parse_results(job_id)**：
1. 调用 `ResultParserService.parse(job_id)`
2. 成功 → 更新 Job status=SUCCESS
3. 异常 → 更新 Job status=FAILED, error_msg

**步骤日志匹配规则**（reV pipeline 日志格式）：

```
INFO - reV.pipeline.pipeline - Completed step: generation
INFO - reV.pipeline.pipeline - Completed step: supply-curve-aggregation
```

Worker 按行读取 pipeline 日志，匹配模式 `Completed step: {step_name}` 来更新对应 JobStep.status=SUCCESS。

---

### 8.3 reV CLI subprocess 封装规范

```python
import subprocess
import shlex

def run_rev_pipeline(config_path, log_path):
    # 返回 subprocess 退出码。
    # 使用 bufsize=1 行缓冲实时输出。
    # stdout/stderr 合并写入 log_path。
    # 不使用 shell=True，避免命令注入。
    cmd = f"reV pipeline -c {config_path}"
    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            shlex.split(cmd),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        proc.wait()
    return proc.returncode
```

**重要约束**：
- 不使用 `shell=True`（避免命令注入）
- 不将用户输入直接插入命令字符串；所有路径从数据库读取，并在生成时做路径合法性校验
- 超时控制：设置 Celery task soft_time_limit（如 6h），超时后发送 SIGTERM，更新 Job status=FAILED

---

### 8.4 日志收集与回填规范

每个 JobStep 的日志文件路径存储在 `JobStep.log_path`。日志内容不入库，只记录文件路径。

API `GET /jobs/{id}/steps/{step_name}/log?lines=200` 由 `JobStatusService.read_log_tail()` 实现，使用 `collections.deque(maxlen=N)` 读取文件末尾 N 行，避免加载整个日志文件。

---

## 9. 结果解析规范

### 9.1 供应曲线 CSV 字段映射

reV supply-curve 模块输出的 `_sc.csv` 标准列到 `ScPoint` DB 字段的映射：

| reV CSV 列名 | ScPoint 字段 | 类型 | 单位 |
|---|---|---|---|
| `sc_point_gid` | `sc_gid` | INT | — |
| `latitude` | `latitude` | DOUBLE | 度 |
| `longitude` | `longitude` | DOUBLE | 度 |
| `capacity` | `capacity_ac_mw` | FLOAT | MW |
| `mean_cf` | `capacity_factor_ac` | FLOAT | 0-1 |
| `mean_annual_energy` | `annual_energy_mwh` | FLOAT | MWh/yr |
| `mean_lcoe` | `lcoe_site_usd_per_mwh` | FLOAT | $/MWh |
| `lcot` | `lcot_usd_per_mwh` | FLOAT | $/MWh |
| `total_lcoe` | `lcoe_all_in_usd_per_mwh` | FLOAT | $/MWh |
| `area_sq_km` | `area_developable_sq_km` | FLOAT | km2 |
| `trans_gid` | `trans_gid` | INT | — |
| `trans_type` | `trans_type` | VARCHAR | — |
| `dist_spur_km` | `dist_spur_km` | FLOAT | km |

**入库 Pydantic Schema（验证层）**：

```python
from pydantic import BaseModel, Field

class ScPointSchema(BaseModel):
    sc_gid: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capacity_ac_mw: float = Field(ge=0)
    capacity_factor_ac: float = Field(ge=0, le=1)
    annual_energy_mwh: float = Field(ge=0)
    lcoe_site_usd_per_mwh: float = Field(ge=0)
    lcot_usd_per_mwh: float = Field(ge=0)
    lcoe_all_in_usd_per_mwh: float = Field(ge=0)
    area_developable_sq_km: float = Field(ge=0)
    trans_gid: int | None = None
    trans_type: str | None = None
    dist_spur_km: float | None = Field(default=None, ge=0)
```

**批量入库策略**：以 1000 行为一批使用 `INSERT ... ON CONFLICT (job_id, sc_gid) DO UPDATE` 实现幂等性，支持重试后重跑不产生重复数据。

---

### 9.2 代表性曲线存储策略

rep-profiles 输出为一个 HDF5 文件（`_rep_profiles.h5`），包含：
- `profiles` dataset：shape `(n_regions × n_res_classes, 8760)`，float32
- `meta` dataset：每行对应一条曲线的区域/等级元数据

**存储方案**：整个 HDF5 文件上传至 MinIO；数据库仅存储元数据（file path、region、res_class、profile_index）。前端通过 presigned URL 直接下载原始 HDF5，或通过专用解析接口提取单条时序数据。

不推荐将每条时序数据展开存入 PostgreSQL：8760 行 × n_profiles 行数巨大，查询性能差，且 HDF5 格式本身对时序数据已有良好的压缩和随机访问支持。

---

### 9.3 结果完整性验证规则

解析完成后执行以下验证，失败时记录告警日志（不回滚已入库数据，但可标记 Job 为 `SUCCESS_WITH_WARNINGS`）：

| 验证项 | 说明 |
|---|---|
| ScPoint 行数 > 0 | 供应曲线点不为空 |
| mean(capacity_factor_ac) > 0.05 | 平均容量因子合理（>5%）|
| 核心指标字段无 NaN | lcoe / capacity / cf 三列无空值 |
| lcoe_all_in >= lcoe_site | 全成本 LCOE 不低于场址 LCOE |
| 点数量与预期格网密度偏差 < 30% | 偏差超过阈值触发告警 |

---

## 10. 输入验证规范

### 10.1 校验时机

| 时机 | 模块 | 校验内容 |
|---|---|---|
| POST /datasets | DatasetService.create | path_pattern 格式是否含 `{year}` 占位符 |
| POST /turbine-templates | TurbineTemplateService.validate_power_curve | 功率曲线长度匹配、切出风速处出力归零 |
| POST /scenarios | ScenarioService.validate | analysis_years 是 Dataset.analysis_years 子集 |
| POST /scenarios/{id}/validate | ScenarioService.validate | HDF5 文件可达性、trans_table_fpath 存在性 |
| ConfigGeneratorService.generate_all | 生成前 | 所有外键实体非空，工作目录可写 |
| ResultParserService.parse_supply_curve | 每行 | Pydantic ScPointSchema 字段范围 |

### 10.2 校验检查项清单

**Dataset 校验**：
- `path_pattern` 包含 `{year}` 且路径合法（无 `..` 等路径穿越）
- `analysis_years` 非空，年份范围 1900–2100
- `crs` 格式为 `EPSG:XXXX`

**TurbineTemplate 校验**：
- `power_curve_json` 两个数组长度相同
- 风速序列严格单调递增
- 切出风速（数组末尾第二个风速）处出力应为 0 或接近 0（不超过额定功率的 1%）
- `system_capacity_kw` > 0，`hub_height_m` 在 (10, 300) 范围内，`rotor_diameter_m` 在 (10, 300) 范围内
- `losses_pct` 在 [0, 50] 范围内

**Scenario 校验**：
- `analysis_years` 是 `Dataset.analysis_years` 的子集
- `power_density_mw_km2` 在 (0.1, 20) 范围内
- `resolution` 在 {32, 64, 128} 枚举中
- `fixed_charge_rate` 在 (0, 1) 范围内
- `output_request` 中的字段名在 reV 已知输出字段白名单内

**ExclusionRule 校验**：
- `rule_type=range` 时 `inclusion_range_min < inclusion_range_max`
- `weight` 在 [0, 1] 范围内
- 关联 `ExclusionLayer.h5_fpath` 文件存在

---

## 11. 部署与运行环境

### 11.1 本地开发环境

使用 Docker Compose 启动所有依赖服务：

```yaml
services:
  db:
    image: postgis/postgis:15-3.4
    environment:
      POSTGRES_DB: rev_siting
      POSTGRES_USER: rev
      POSTGRES_PASSWORD: dev_password
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"

  api:
    build: .
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    volumes:
      - ./:/app
      - /data/wtk:/data/wtk:ro
      - /data/jobs:/data/jobs
    depends_on: [db, redis, minio]

  worker:
    build: .
    command: celery -A app.worker.celery_app worker --loglevel=info
    volumes:
      - ./:/app
      - /data/wtk:/data/wtk:ro
      - /data/jobs:/data/jobs
    depends_on: [db, redis]
```

### 11.2 生产部署最小化需求

| 组件 | 最低规格 | 说明 |
|---|---|---|
| API 服务 | 2 vCPU / 4 GB RAM | FastAPI + Uvicorn |
| Celery Worker | 8 vCPU / 32 GB RAM | reV generation 内存密集 |
| PostgreSQL | 4 vCPU / 16 GB RAM | ScPoint 表可能有百万行级别 |
| Redis | 1 vCPU / 2 GB RAM | Celery broker 使用量小 |
| MinIO | 2 vCPU / 8 GB RAM + 500 GB 存储 | HDF5 结果文件 |
| WTK HDF5 存储 | — | 本地 NFS 或 HSDS 服务 |

### 11.3 目录结构与权限规范

```
/data/
+-- wtk/              # WTK HDF5 文件（只读挂载，API/worker 均可读）
+-- exclusions/       # Exclusions HDF5 文件（只读）
+-- transmission/     # 输电线路 CSV 文件（只读）
+-- jobs/             # 任务工作目录（worker 可读写，API 可读）
    +-- {job_id}/
```

- API 进程以最小权限用户运行，只需读取 `/data/jobs/` 下的日志和结果文件
- Worker 进程需要对 `/data/jobs/` 的读写权限
- 数据库凭据通过环境变量注入，不硬编码在代码或配置文件中

---

## 12. 分阶段实施路径

### Phase 1：单点 MVP（必须实现）

目标：能够对单年数据的单个区域执行一次完整的 reV pipeline 并查看结果。

**必须实现**：
- [ ] PostgreSQL schema 迁移（Dataset / TurbineTemplate / Scenario / Job / JobStep / ScPoint）
- [ ] DatasetService、TurbineTemplateService、ScenarioService 的 CRUD
- [ ] ConfigGeneratorService（generation + supply-curve-aggregation + supply-curve）
- [ ] JobRunnerService（local subprocess，无 Celery，同步调用）
- [ ] 简单的 ResultParserService（_sc.csv → ScPoint 入库）
- [ ] REST API：/datasets, /turbine-templates, /scenarios, /jobs
- [ ] GET /jobs/{id}/supply-curve（无过滤，全量返回）

**验收标准**：使用 reV 提供的测试数据集，能端到端完成一次风电宏观选址分析，供应曲线点成功入库并可通过 API 查询。

---

### Phase 2：区域级完整链路

目标：支持多年分析、排除规则、输电成本、异步任务执行。

**新增实现**：
- [ ] Celery + Redis 异步任务队列
- [ ] 多年数据支持（collect 步骤 + multi-year 聚合）
- [ ] ExclusionService 及排除规则管理
- [ ] TransmissionNetwork 管理
- [ ] JobRunnerService 重构为异步（Celery chain）
- [ ] JobStatusService（步骤状态 + 日志尾部查看）
- [ ] ResultQueryService（过滤 + 分页 + 摘要统计）
- [ ] GET /jobs/{id}/supply-curve/export（CSV 流式下载）
- [ ] POST /scenarios/{id}/validate（前置校验接口）

**验收标准**：能够对 3 年数据、带排除规则的完整场景执行分析，任务失败后可查看步骤日志，可重试。

---

### Phase 3：生产化增强（可选）

目标：提升可靠性、可观测性和可扩展性。

**可选增强**：
- [ ] RepProfile 支持（rep-profiles 步骤 + MinIO）
- [ ] 场景对比接口（并排展示多个 job 的供应曲线摘要）
- [ ] 输入数据预校验（HDF5 格式验证、坐标完整性）
- [ ] Celery beat 定期清理过期任务工作目录
- [ ] 结果导出为 GeoPackage / Shapefile 格式
- [ ] OpenTelemetry 链路追踪接入
- [ ] 多租户权限模型（场景/任务按用户隔离）
- [ ] SLURM 执行控制选项（将 execution_control.option 改为 eagle/slurm）

---

*文档版本 v1.0 — 基于 reV 0.15.0 编写*
