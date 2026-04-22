# reV 风电场宏观选址软件开发详细设计文档

## 文档版本信息

| 版本 | 日期 | 作者 | 修订说明 |
|------|------|------|----------|
| V1.0 | 2024-01 | 技术团队 | 初始版本 |

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构设计](#2-系统架构设计)
3. [功能模块设计](#3-功能模块设计)
4. [数据模型设计](#4-数据模型设计)
5. [算法详细设计](#5-算法详细设计)
6. [接口设计](#6-接口设计)
7. [数据库设计](#7-数据库设计)
8. [系统部署设计](#8-系统部署设计)
9. [开发规范与标准](#9-开发规范与标准)
10. [测试策略](#10-测试策略)
11. [性能优化方案](#11-性能优化方案)
12. [项目实施计划](#12-项目实施计划)

---

## 1. 项目概述

### 1.1 项目背景

本项目旨在基于 NREL reV（Renewable Energy Potential Model）开源框架，开发一套完整的风电场宏观选址软件系统。该系统将为风电开发商、政策制定者和研究机构提供从区域资源评估到具体站点优化的全流程技术支持。

### 1.2 建设目标

#### 1.2.1 总体目标
构建一个高性能、可扩展、易用的风电场宏观选址软件平台，实现：
- 大范围区域风能资源技术潜力评估
- 多约束条件下的可用土地识别
- 风电场布局自动优化
- 技术经济性分析
- 可视化展示与决策支持

#### 1.2.2 具体技术指标
- 支持千万级网格单元的大规模计算
- 单次区域评估计算时间 < 24小时（并行环境下）
- 单点优化计算时间 < 2小时
- 系统可用性 > 99%
- 支持并发用户数 ≥ 50
- 数据处理能力：≥ 100 GB/小时

### 1.3 技术路线

基于 reV 核心引擎，采用微服务架构，结合现代 Web 技术和云计算平台，构建分层解耦的软件系统。

**核心技术栈**：
- **后端**: Python 3.11+, FastAPI, Celery
- **前端**: Vue.js 3, ECharts, Mapbox GL
- **数据库**: PostgreSQL + PostGIS, Redis, MinIO
- **计算引擎**: reV, SAM, Dask
- **部署**: Docker, Kubernetes

### 1.4 适用范围

本设计文档适用于：
- 系统架构师进行技术选型和架构设计
- 后端开发工程师实现业务逻辑
- 前端开发工程师实现用户界面
- 测试工程师制定测试方案
- 运维工程师进行系统部署和维护

---

## 2. 系统架构设计

### 2.1 总体架构

系统采用分层微服务架构，分为以下层次：

```
┌─────────────────────────────────────────┐
│          表现层 (Presentation)           │
│  ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Web 前端  │ │ 移动应用  │ │ API网关 │  │
│  └──────────┘ └──────────┘ └────────┘  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          应用层 (Application)            │
│  ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │项目管理│ │任务调度│ │ 用户认证   │  │
│  └────────┘ └────────┘ └────────────┘  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          服务层 (Services)               │
│  ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │资源评估│ │排除分析│ │ 供应曲线   │  │
│  └────────┘ └────────┘ └────────────┘  │
│  ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │bespoke │ │经济分析│ │ 传输成本   │  │
│  └────────┘ └────────┘ └────────────┘  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          核心引擎层 (Core Engine)        │
│  ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │  reV   │ │  SAM   │ │   rex      │  │
│  └────────┘ └────────┘ └────────────┘  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          数据层 (Data)                   │
│  ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │PostgreSQL│ │ Redis  │ │  MinIO     │  │
│  └────────┘ └────────┘ └────────────┘  │
└─────────────────────────────────────────┘
```

### 2.2 微服务划分

#### 2.2.1 用户服务 (user-service)
- **职责**: 用户注册、登录、权限管理
- **技术**: FastAPI + JWT + OAuth2
- **端口**: 8001

#### 2.2.2 项目管理服务 (project-service)
- **职责**: 项目创建、配置管理、元数据存储
- **技术**: FastAPI + PostgreSQL
- **端口**: 8002

#### 2.2.3 计算任务服务 (compute-service)
- **职责**: 任务提交、状态跟踪、结果查询
- **技术**: FastAPI + Celery + Redis
- **端口**: 8003

#### 2.2.4 资源评估服务 (resource-service)
- **职责**: 风能资源数据处理、统计分析
- **技术**: reV + Dask
- **端口**: 8004

#### 2.2.5 排除分析服务 (exclusion-service)
- **职责**: 土地利用约束分析、可用土地识别
- **技术**: reV + GeoPandas
- **端口**: 8005

#### 2.2.6 供应曲线服务 (supply-curve-service)
- **职责**: 供应曲线聚合、技术潜力计算
- **技术**: reV Supply Curve模块
- **端口**: 8006

#### 2.2.7 Bespoke 优化服务 (bespoke-service)
- **职责**: 风电场布局优化、涡轮机排布
- **技术**: reV Bespoke模块
- **端口**: 8007

#### 2.2.8 经济分析服务 (econ-service)
- **职责**: LCOE计算、成本效益分析
- **技术**: reV Econ模块 + NRWAL
- **端口**: 8008

#### 2.2.9 可视化服务 (visualization-service)
- **职责**: 地图渲染、图表生成、报告输出
- **技术**: FastAPI + Matplotlib + Plotly
- **端口**: 8009

### 2.3 数据流架构

```
用户请求 → API网关 → 任务队列 → 工作节点 → 结果存储 → 通知用户
                ↓
          元数据数据库
                ↓
          对象存储(输入/输出数据)
```

### 2.4 技术选型理由

| 技术 | 选型理由 |
|------|---------|
| **FastAPI** | 高性能异步框架，自动生成API文档，类型安全 |
| **Celery** | 成熟的分布式任务队列，支持定时任务和重试 |
| **PostgreSQL + PostGIS** | 强大的空间数据处理能力，ACID保证 |
| **Redis** | 高速缓存和消息代理，支持发布订阅 |
| **MinIO** | S3兼容的对象存储，适合大规模地理空间数据 |
| **Dask** | 并行计算框架，处理超大规模数据集 |
| **Vue.js 3** | 响应式前端框架，组件化开发 |
| **Mapbox GL** | 高性能矢量地图渲染 |

---

## 3. 功能模块设计

### 3.1 用户管理模块

#### 3.1.1 功能描述
提供用户注册、登录、权限控制、个人信息管理等功能。

#### 3.1.2 核心类设计

```python
from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

class UserModel(BaseModel):
    """用户数据模型"""
    id: UUID
    username: str
    email: EmailStr
    hashed_password: str
    role: UserRole
    created_at: datetime
    is_active: bool

class UserService:
    """用户服务类"""
    
    async def create_user(self, user_data: dict) -> UserModel:
        """创建新用户"""
        # 实现用户创建逻辑
        pass
    
    async def authenticate(self, username: str, password: str) -> dict:
        """用户认证，返回JWT token"""
        # 实现认证逻辑
        pass
    
    async def get_user_profile(self, user_id: UUID) -> UserModel:
        """获取用户信息"""
        pass
    
    async def update_user_role(self, user_id: UUID, role: UserRole) -> UserModel:
        """更新用户角色"""
        pass
```

#### 3.1.3 API 接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 注册用户 | POST | /api/v1/users/register | 公开接口 |
| 用户登录 | POST | /api/v1/users/login | 返回JWT |
| 获取用户信息 | GET | /api/v1/users/me | 需要认证 |
| 更新用户信息 | PUT | /api/v1/users/me | 需要认证 |
| 用户列表 | GET | /api/v1/users | 仅管理员 |

### 3.2 项目管理模块

#### 3.2.1 功能描述
管理风电场选址项目，包括项目创建、配置管理、数据关联等。

#### 3.2.2 数据模型

```python
from typing import List, Dict, Optional
from enum import Enum

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class AnalysisType(str, Enum):
    SUPPLY_CURVE = "supply_curve"
    BESPOKE = "bespoke"
    BOTH = "both"

class ProjectConfig(BaseModel):
    """项目配置"""
    resource_files: List[str]  # 资源文件路径
    exclusion_files: List[str]  # 排除文件路径
    sam_config: Dict  # SAM配置
    analysis_type: AnalysisType
    parameters: Dict  # 分析参数
    techmap_dataset: str  # 技术映射数据集名称

class ProjectModel(BaseModel):
    """项目数据模型"""
    id: UUID
    name: str
    description: str
    owner_id: UUID
    region: Dict  # 地理边界 GeoJSON
    config: ProjectConfig
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
```

#### 3.2.3 核心业务流程

```
创建项目 → 上传/选择数据 → 配置参数 → 验证配置 → 保存项目
```

### 3.3 资源评估模块

#### 3.3.1 功能描述
加载和处理风能资源数据，提供统计分析和可视化。

#### 3.3.2 核心类设计

```python
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict
from rex.multi_year_resource import MultiYearWindResource

class WindStats(BaseModel):
    """风能统计指标"""
    mean_ws: float  # 平均风速
    std_ws: float  # 风速标准差
    max_ws: float  # 最大风速
    weibull_a: float  # 威布尔尺度参数
    weibull_k: float  # 威布尔形状参数
    wind_rose: np.ndarray  # 风玫瑰数据

class ResourceAssessmentService:
    """资源评估服务"""
    
    def __init__(self, resource_files: List[str]):
        self.resource_handler = MultiYearWindResource(resource_files)
    
    def get_wind_statistics(self, gids: List[int], hub_height: int) -> WindStats:
        """计算风能统计指标"""
        ws = self.resource_handler[f'windspeed_{hub_height}m', :, gids]
        wd = self.resource_handler[f'winddirection_{hub_height}m', :, gids]
        
        return WindStats(
            mean_ws=np.mean(ws),
            std_ws=np.std(ws),
            max_ws=np.max(ws),
            weibull_a=self._fit_weibull(ws)[0],
            weibull_k=self._fit_weibull(ws)[1],
            wind_rose=self._build_wind_rose(ws, wd)
        )
    
    def get_time_series(self, gid: int, hub_height: int, 
                       start_date: str, end_date: str) -> pd.DataFrame:
        """提取时间序列数据"""
        # 实现时间序列提取
        pass
    
    def _fit_weibull(self, wind_speeds: np.ndarray) -> Tuple[float, float]:
        """拟合威布尔分布"""
        from scipy.stats import weibull_min
        shape, loc, scale = weibull_min.fit(wind_speeds, floc=0)
        return scale, shape
    
    def _build_wind_rose(self, ws: np.ndarray, wd: np.ndarray,
                        wd_bins: Tuple = (0, 360, 12),
                        ws_bins: Tuple = (0, 25, 5)) -> np.ndarray:
        """构建风玫瑰图"""
        # 实现风玫瑰频率分布计算
        pass
```

#### 3.3.3 性能优化策略

- **数据预加载**: 使用 `BespokeMultiPlantData` 预加载常用数据
- **缓存机制**: Redis 缓存统计结果
- **并行处理**: Dask 并行处理多个 GID
- **分块读取**: HDF5 分块读取避免内存溢出

### 3.4 排除分析模块

#### 3.4.1 功能描述
基于多层地理约束条件，识别可用于风电开发的土地。

#### 3.4.2 核心算法流程

```python
from scipy import ndimage
from typing import Dict

class ExclusionResult(BaseModel):
    """排除分析结果"""
    inclusion_mask: np.ndarray  # 2D 二进制掩膜
    available_area_km2: float  # 可用面积
    excluded_area_km2: float  # 排除面积
    exclusion_breakdown: Dict[str, float]  # 各层排除面积统计
    contiguous_regions: int  # 连续区域数量
    largest_region_km2: float  # 最大连续区域面积

class ExclusionAnalysisService:
    """排除分析服务"""
    
    def __init__(self, exclusion_file: str, excl_dict: Dict, 
                 min_area: float = None):
        self.excl_handler = ExclusionLayers(exclusion_file)
        self.excl_dict = excl_dict
        self.min_area = min_area
        self.pixel_area_km2 = self._calculate_pixel_area()
    
    def generate_inclusion_mask(self) -> ExclusionResult:
        """生成包含掩膜"""
        # 1. 初始化全True掩膜
        mask = np.ones(self.excl_handler.shape, dtype=bool)
        exclusion_stats = {}
        
        # 2. 逐层应用排除规则
        for layer_name, layer_config in self.excl_dict.items():
            layer_data = self.excl_handler[layer_name]
            layer_mask = self._apply_layer_rule(layer_data, layer_config)
            
            # 统计该层排除面积
            excluded_pixels = np.sum(mask & ~layer_mask)
            exclusion_stats[layer_name] = excluded_pixels * self.pixel_area_km2
            
            mask = mask & layer_mask
        
        # 3. 连续区域过滤
        if self.min_area:
            mask = self._filter_contiguous_areas(mask, self.min_area)
        
        # 4. 计算统计信息
        available_area = np.sum(mask) * self.pixel_area_km2
        total_area = mask.size * self.pixel_area_km2
        
        return ExclusionResult(
            inclusion_mask=mask,
            available_area_km2=available_area,
            excluded_area_km2=total_area - available_area,
            exclusion_breakdown=exclusion_stats,
            contiguous_regions=self._count_contiguous_regions(mask),
            largest_region_km2=self._get_largest_region_area(mask)
        )
    
    def _apply_layer_rule(self, data: np.ndarray, 
                         config: Dict) -> np.ndarray:
        """应用单层排除规则"""
        mask = np.ones(data.shape, dtype=bool)
        
        if 'inclusion_range' in config:
            min_val, max_val = config['inclusion_range']
            if min_val is not None:
                mask = mask & (data >= min_val)
            if max_val is not None:
                mask = mask & (data <= max_val)
        
        if 'exclude_values' in config:
            mask = mask & ~np.isin(data, config['exclude_values'])
        
        if config.get('exclude_nodata', True):
            mask = mask & (data != self.nodata_value)
        
        return mask
    
    def _filter_contiguous_areas(self, mask: np.ndarray, 
                                min_area_km2: float) -> np.ndarray:
        """过滤小于最小面积的连续区域"""
        # 标记连通区域
        labeled, n_features = ndimage.label(mask)
        
        # 计算每个区域的面积
        region_sizes = np.bincount(labeled.ravel()) * self.pixel_area_km2
        
        # 移除小区域
        small_regions = np.where(region_sizes < min_area_km2)[0]
        for region_id in small_regions:
            if region_id > 0:  # 跳过背景
                mask[labeled == region_id] = False
        
        return mask
```

### 3.5 供应曲线聚合模块

#### 3.5.1 功能描述
将研究区域划分为供应曲线点，聚合资源数据和排除信息，计算技术潜力。

#### 3.5.2 核心类设计

```python
from concurrent.futures import ProcessPoolExecutor
from typing import Optional, List

class SupplyCurveAggregationService:
    """供应曲线聚合服务"""
    
    def __init__(self, project_config: ProjectConfig):
        self.excl_fpath = project_config.exclusion_files[0]
        self.res_fpath = project_config.resource_files
        self.tm_dset = project_config.techmap_dataset
        self.resolution = project_config.sc_resolution  # 默认64
        
    def run_aggregation(self, gids: Optional[List[int]] = None) -> pd.DataFrame:
        """执行供应曲线聚合"""
        from reV.supply_curve.aggregation import Aggregation
        
        # 1. 初始化聚合器
        aggregator = Aggregation(
            excl_fpath=self.excl_fpath,
            tm_dset=self.tm_dset,
            res_fpath=self.res_fpath,
            resolution=self.resolution,
            gids=gids
        )
        
        # 2. 执行聚合
        results = []
        for sc_point in aggregator.supply_curve_points:
            try:
                result = self._process_sc_point(sc_point)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process SC point {sc_point.gid}: {e}")
                continue
        
        # 3. 转换为 DataFrame
        return pd.DataFrame(results)
    
    def _process_sc_point(self, sc_point) -> Dict:
        """处理单个供应曲线点"""
        # 1. 获取资源数据
        wind_speeds = self._get_weighted_wind_speeds(sc_point)
        wind_dirs = self._get_weighted_wind_directions(sc_point)
        
        # 2. 运行 SAM 模拟
        sam_outputs = self._run_sam_simulation(wind_speeds, wind_dirs)
        
        # 3. 计算经济指标
        lcoe = self._calculate_lcoe(sam_outputs, sc_point)
        
        # 4. 组装结果
        return {
            'sc_gid': sc_point.gid,
            'latitude': sc_point.latitude,
            'longitude': sc_point.longitude,
            'available_area_km2': sc_point.available_area,
            'capacity_ac_mw': sam_outputs['system_capacity'] / 1000,
            'cf_mean': sam_outputs['cf_mean'],
            'lcoe_real': lcoe,
            'generation_profile': sam_outputs['gen_profile']
        }
```

#### 3.5.3 并行化处理

```python
class ParallelSupplyCurveAggregation:
    """并行供应曲线聚合"""
    
    def __init__(self, n_workers: int = 8):
        self.n_workers = n_workers
        self.executor = ProcessPoolExecutor(max_workers=n_workers)
    
    def run_parallel(self, sc_gids: List[int], 
                    chunk_size: int = 100) -> pd.DataFrame:
        """并行执行聚合"""
        # 分块处理
        chunks = [sc_gids[i:i+chunk_size] 
                 for i in range(0, len(sc_gids), chunk_size)]
        
        futures = []
        for chunk in chunks:
            future = self.executor.submit(
                self._process_chunk, chunk
            )
            futures.append(future)
        
        # 收集结果
        results = []
        for future in futures:
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Chunk processing failed: {e}")
        
        return pd.concat(results, ignore_index=True)
```

### 3.6 Bespoke 优化模块

#### 3.6.1 功能描述
对选定的供应曲线点进行风电场布局优化，确定最优涡轮机位置和数量。

#### 3.6.2 核心类设计

```python
from reV.bespoke.bespoke import BespokeSinglePlant

class BespokeOptimizationService:
    """定制化优化服务"""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
    
    def optimize_single_plant(self, sc_gid: int, 
                             objective_function: str,
                             cost_functions: Dict) -> Dict:
        """优化单个风电场布局"""
        
        # 1. 创建 BespokeSinglePlant 实例
        bsp = BespokeSinglePlant(
            gid=sc_gid,
            excl=self.config.exclusion_files[0],
            res=self.config.resource_files,
            tm_dset=self.config.techmap_dataset,
            sam_sys_inputs=self.config.sam_config,
            objective_function=objective_function,
            capital_cost_function=cost_functions['capital'],
            fixed_operating_cost_function=cost_functions['fixed_om'],
            variable_operating_cost_function=cost_functions['variable_om'],
            balance_of_system_cost_function=cost_functions['bos'],
            min_spacing='5x',
            excl_dict=self.config.exclusion_config,
            output_request=('system_capacity', 'cf_mean', 'cf_profile'),
            ga_kwargs={'max_time': 3600}  # 1小时超时
        )
        
        # 2. 运行优化
        results = bsp.run_plant_optimization()
        
        # 3. 提取关键结果
        return {
            'sc_gid': sc_gid,
            'n_turbines': results['n_turbines'],
            'system_capacity': results['system_capacity'],
            'turbine_x_coords': results['turbine_x_coords'],
            'turbine_y_coords': results['turbine_y_coords'],
            'bespoke_aep': results['bespoke_aep'],
            'bespoke_cf_mean': results['bespoke_cf_mean'],
            'capital_cost': results['capital_cost'],
            'lcoe': results['total_lcoe']
        }
    
    def batch_optimize(self, sc_gids: List[int]) -> List[Dict]:
        """批量优化多个站点"""
        results = []
        for gid in sc_gids:
            try:
                result = self.optimize_single_plant(gid)
                results.append(result)
            except Exception as e:
                logger.error(f"Optimization failed for GID {gid}: {e}")
                continue
        return results
```

### 3.7 经济分析模块

#### 3.7.1 功能描述
计算平准化能源成本（LCOE），进行成本效益分析。

#### 3.7.2 核心算法

```python
class EconomicAnalysisService:
    """经济分析服务"""
    
    def calculate_lcoe(self, capital_cost: float,
                      fixed_om: float,
                      variable_om: float,
                      annual_energy: float,
                      fixed_charge_rate: float = 0.079) -> float:
        """
        计算 LCOE
        
        公式: LCOE = (FCR * Capital + Fixed_OM) / AEP + Variable_OM
        
        参数:
            capital_cost: 资本成本 ($)
            fixed_om: 固定运维成本 ($/年)
            variable_om: 可变运维成本 ($/kWh)
            annual_energy: 年发电量 (kWh/年)
            fixed_charge_rate: 固定收费率
        
        返回:
            lcoe: 平准化能源成本 ($/MWh)
        """
        if annual_energy == 0:
            return float('inf')
        
        lcoe = ((fixed_charge_rate * capital_cost + fixed_om) / 
                annual_energy + variable_om)
        
        # 转换为 $/MWh
        return lcoe * 1000
```

### 3.8 可视化模块

#### 3.8.1 功能描述
生成地图、图表和报告，直观展示分析结果。

#### 3.8.2 核心功能

```python
import matplotlib.pyplot as plt
import plotly.express as px

class VisualizationService:
    """可视化服务"""
    
    def generate_supply_curve_map(self, results: pd.DataFrame) -> str:
        """生成供应曲线地图"""
        # 使用 Plotly 生成交互式地图
        fig = px.scatter_mapbox(
            results,
            lat='latitude',
            lon='longitude',
            color='lcoe_real',
            size='capacity_ac_mw',
            hover_data=['sc_gid', 'cf_mean'],
            color_continuous_scale='Viridis',
            zoom=5
        )
        fig.update_layout(mapbox_style="carto-positron")
        
        # 保存为 HTML
        output_path = "/tmp/supply_curve_map.html"
        fig.write_html(output_path)
        return output_path
    
    def generate_wind_rose_chart(self, wind_rose_data: np.ndarray) -> str:
        """生成风玫瑰图"""
        # 使用 Matplotlib 生成风玫瑰图
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        # 绘制逻辑...
        
        output_path = "/tmp/wind_rose.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        return output_path
    
    def generate_lcoe_histogram(self, results: pd.DataFrame) -> str:
        """生成 LCOE 直方图"""
        fig = px.histogram(
            results,
            x='lcoe_real',
            nbins=50,
            title='LCOE Distribution'
        )
        
        output_path = "/tmp/lcoe_histogram.html"
        fig.write_html(output_path)
        return output_path
```

---

## 4. 数据模型设计

### 4.1 数据库 ER 图

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│    users     │       │   projects   │       │  tasks       │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │───┐   │ id (PK)      │───┐   │ id (PK)      │
│ username     │   └──<│ owner_id(FK) │   └──<│ project_id(FK)│
│ email        │       │ name         │       │ status       │
│ password_hash│       │ description  │       │ task_type    │
│ role         │       │ region       │       │ config       │
│ created_at   │       │ config       │       │ result_path  │
│ is_active    │       │ status       │       │ created_at   │
└──────────────┘       │ created_at   │       │ completed_at │
                       └──────────────┘       └──────────────┘
                              │
                              │
                       ┌──────────────┐
                       │project_data  │
                       ├──────────────┤
                       │ id (PK)      │
                       │ project_id(FK)│
                       │ data_type    │
                       │ file_path    │
                       │ metadata     │
                       └──────────────┘
```

### 4.2 主要数据表设计

#### 4.2.1 用户表 (users)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

#### 4.2.2 项目表 (projects)

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    region JSONB,  -- GeoJSON geometry
    config JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_projects_owner ON projects(owner_id);
CREATE INDEX idx_projects_status ON projects(status);
```

#### 4.2.3 任务表 (tasks)

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    task_type VARCHAR(50) NOT NULL,  -- 'supply_curve', 'bespoke', etc.
    status VARCHAR(20) DEFAULT 'pending',
    config JSONB,
    result_path VARCHAR(500),
    error_message TEXT,
    progress FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
```

### 4.3 文件存储结构

```
minio-storage/
├── resources/              # 资源数据
│   ├── wtk_conus/
│   │   ├── wtk_conus_2012.h5
│   │   └── wtk_conus_2013.h5
├── exclusions/             # 排除数据
│   ├── conus_exclusions.h5
│   └── state_exclusions/
├── projects/               # 项目数据
│   ├── {project_id}/
│   │   ├── config.json
│   │   ├── inputs/
│   │   └── outputs/
│   │       ├── supply_curve_results.csv
│   │       ├── bespoke_results.h5
│   │       └── visualizations/
└── temp/                   # 临时文件
```

---

## 5. 算法详细设计

### 5.1 排除分析算法

#### 5.1.1 算法流程

```
开始
  ↓
初始化全True掩膜
  ↓
遍历每个排除图层
  ↓
应用图层规则（范围/值排除）
  ↓
与主掩膜进行逻辑AND
  ↓
所有图层处理完成？
  ↓ 是
连续区域过滤
  ↓
计算面积统计
  ↓
返回结果
```

#### 5.1.2 复杂度分析

- **时间复杂度**: O(L × N)，L为图层数，N为网格单元数
- **空间复杂度**: O(N)，存储掩膜数组

### 5.2 遗传算法优化

#### 5.2.1 算法参数

```python
GA_CONFIG = {
    'max_generation': 10000,      # 最大代数
    'population_size': 25,         # 种群大小
    'crossover_rate': 0.2,         # 交叉概率
    'mutation_rate': 0.01,         # 变异概率
    'tol': 1E-6,                   # 收敛容差
    'convergence_iters': 10000,    # 收敛迭代次数
    'max_time': 3600               # 最大运行时间(秒)
}
```

#### 5.2.2 算法流程

```
初始化种群（随机二进制串）
  ↓
评估每个个体的适应度
  ↓
while 未满足终止条件:
  ↓
  选择操作（锦标赛选择）
  ↓
  交叉操作（单点交叉）
  ↓
  变异操作（位翻转）
  ↓
  评估新种群适应度
  ↓
  精英保留
  ↓
  检查收敛
  ↓
返回最优个体
```

#### 5.2.3 适应度函数

```python
def fitness_function(chromosome, candidate_locations, sam_config):
    """
    适应度函数（最小化 LCOE）
    
    参数:
        chromosome: 二进制染色体
        candidate_locations: 候选涡轮机位置
        sam_config: SAM 配置
    
    返回:
        objective_value: 目标函数值（LCOE）
    """
    # 解码染色体
    selected = [bool(gene) for gene in chromosome]
    n_turbines = sum(selected)
    
    if n_turbines == 0:
        return float('inf')
    
    # 获取选中位置
    x_locs = candidate_locations.x[selected]
    y_locs = candidate_locations.y[selected]
    
    # 运行 SAM 模拟
    system_capacity = n_turbines * turbine_rating
    aep = run_sam_simulation(x_locs, y_locs, system_capacity)
    
    # 计算成本
    capital_cost = 200 * system_capacity * exp(-system_capacity / 1E5 * 0.1)
    fixed_om = 0
    
    # 计算 LCOE
    fcr = sam_config.get('fixed_charge_rate', 0.079)
    lcoe = (fcr * capital_cost + fixed_om) / aep
    
    return lcoe
```

### 5.3 资源聚合算法

#### 5.3.1 加权平均算法

```python
def weighted_aggregation(data, weights):
    """
    加权聚合
    
    参数:
        data: 数据数组 (time, space)
        weights: 权重数组 (space,)
    
    返回:
        aggregated: 聚合后的时间序列 (time,)
    """
    # 归一化权重
    weights_normalized = weights / weights.sum()
    
    # 加权求和
    aggregated = np.sum(data * weights_normalized, axis=1)
    
    return aggregated
```

#### 5.3.2 风向矢量平均

```python
def circular_mean_direction(directions_deg, weights):
    """
    计算圆形平均风向
    
    参数:
        directions_deg: 风向数组（度）
        weights: 权重数组
    
    返回:
        mean_direction: 平均风向（度，0-360）
    """
    # 转换为弧度
    angles = np.radians(directions_deg)
    
    # 计算正弦和余弦的加权和
    sin_sum = np.sum(np.sin(angles) * weights, axis=1)
    cos_sum = np.sum(np.cos(angles) * weights, axis=1)
    
    # 计算平均角度
    mean_angles = np.arctan2(sin_sum, cos_sum)
    mean_directions = np.degrees(mean_angles)
    
    # 转换到 0-360 范围
    mean_directions[mean_directions < 0] += 360
    
    return mean_directions
```

---

## 6. 接口设计

### 6.1 RESTful API 设计

#### 6.1.1 用户接口

```yaml
POST /api/v1/users/register:
  summary: 用户注册
  request:
    body:
      username: string
      email: string
      password: string
  response:
    201:
      user_id: UUID
      message: "User created successfully"

POST /api/v1/users/login:
  summary: 用户登录
  request:
    body:
      username: string
      password: string
  response:
    200:
      access_token: string
      token_type: "bearer"
      expires_in: 3600
```

#### 6.1.2 项目接口

```yaml
POST /api/v1/projects:
  summary: 创建项目
  security:
    - bearerAuth: []
  request:
    body:
      name: string
      description: string
      region: GeoJSON
      config: ProjectConfig
  response:
    201:
      project_id: UUID
      status: "draft"

GET /api/v1/projects/{project_id}:
  summary: 获取项目详情
  security:
    - bearerAuth: []
  response:
    200:
      project: ProjectModel

PUT /api/v1/projects/{project_id}:
  summary: 更新项目
  security:
    - bearerAuth: []
  request:
    body:
      name?: string
      description?: string
      config?: ProjectConfig
```

#### 6.1.3 任务接口

```yaml
POST /api/v1/projects/{project_id}/tasks:
  summary: 提交计算任务
  security:
    - bearerAuth: []
  request:
    body:
      task_type: "supply_curve" | "bespoke"
      parameters: Dict
  response:
    202:
      task_id: UUID
      status: "pending"

GET /api/v1/tasks/{task_id}:
  summary: 查询任务状态
  security:
    - bearerAuth: []
  response:
    200:
      task_id: UUID
      status: "pending" | "running" | "completed" | "failed"
      progress: float
      result_path?: string

GET /api/v1/tasks/{task_id}/results:
  summary: 获取任务结果
  security:
    - bearerAuth: []
  response:
    200:
      data: Any
      download_url?: string
```

### 6.2 WebSocket 实时通知

```python
from fastapi import WebSocket

class TaskNotificationService:
    """任务通知服务"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket
    
    async def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
    
    async def send_progress_update(self, task_id: str, progress: float):
        if task_id in self.active_connections:
            await self.active_connections[task_id].send_json({
                "type": "progress",
                "task_id": task_id,
                "progress": progress
            })
    
    async def send_completion_notification(self, task_id: str, 
                                          status: str, result_path: str = None):
        if task_id in self.active_connections:
            await self.active_connections[task_id].send_json({
                "type": "completion",
                "task_id": task_id,
                "status": status,
                "result_path": result_path
            })
```

---

## 7. 数据库设计

### 7.1 PostgreSQL 配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: rev_wind_siting
      POSTGRES_USER: rev_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

### 7.2 索引优化

```sql
-- 空间索引
CREATE INDEX idx_projects_region_gist ON projects USING GIST (
    ST_GeomFromGeoJSON(region->>'geometry')
);

-- 复合索引
CREATE INDEX idx_tasks_project_status ON tasks(project_id, status);

-- JSONB 索引
CREATE INDEX idx_projects_config_gin ON projects USING GIN (config);
```

---

## 8. 系统部署设计

### 8.1 Docker 容器化

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 Kubernetes 部署

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rev-compute-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: rev-compute
  template:
    metadata:
      labels:
        app: rev-compute
    spec:
      containers:
      - name: compute
        image: rev/compute-service:latest
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        env:
        - name: REDIS_URL
          value: "redis://redis:6379"
        - name: DB_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: database-url
```

### 8.3 监控与日志

```yaml
# Prometheus 监控配置
monitoring:
  metrics_endpoint: "/metrics"
  scrape_interval: 15s
  
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

---

## 9. 开发规范与标准

### 9.1 代码规范

- **Python**: 遵循 PEP 8，使用 Black 格式化
- **类型注解**: 所有函数必须添加类型注解
- **文档字符串**: 使用 Google 风格 docstring
- **命名规范**: 
  - 变量/函数: snake_case
  - 类: PascalCase
  - 常量: UPPER_CASE

### 9.2 Git 工作流

```
main (protected)
  ↑
  | merge
develop
  ↑
  | merge
feature/xxx  bugfix/xxx  hotfix/xxx
```

**提交信息规范**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

类型: feat, fix, docs, style, refactor, test, chore

### 9.3 测试规范

- **单元测试**: pytest，覆盖率 > 80%
- **集成测试**: 测试 API 端点
- **性能测试**: 基准测试关键算法

---

## 10. 测试策略

### 10.1 测试金字塔

```
       /\
      /  \     E2E Tests (10%)
     /----\
    /      \   Integration Tests (20%)
   /--------\
  /          \ Unit Tests (70%)
 /------------\
```

### 10.2 测试用例示例

```python
import pytest
from fastapi.testclient import TestClient

class TestProjectAPI:
    """项目 API 测试"""
    
    def test_create_project(self, client: TestClient, auth_headers: dict):
        """测试创建项目"""
        payload = {
            "name": "Test Project",
            "description": "Test Description",
            "region": {"type": "Polygon", "coordinates": [...]},
            "config": {...}
        }
        
        response = client.post(
            "/api/v1/projects",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "project_id" in data
        assert data["status"] == "draft"
    
    def test_get_project(self, client: TestClient, auth_headers: dict,
                        test_project_id: UUID):
        """测试获取项目"""
        response = client.get(
            f"/api/v1/projects/{test_project_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_project_id)
```

### 10.3 性能测试

```python
import asyncio
import aiohttp

async def test_concurrent_requests():
    """测试并发请求性能"""
    url = "http://localhost:8000/api/v1/projects"
    headers = {"Authorization": "Bearer test_token"}
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(100):
            task = asyncio.create_task(
                session.get(url, headers=headers)
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # 验证所有请求成功
        assert all(r.status == 200 for r in responses)
```

---

## 11. 性能优化方案

### 11.1 数据库优化

- **连接池**: 使用 SQLAlchemy AsyncEngine
- **查询优化**: 避免 N+1 查询，使用 eager loading
- **读写分离**: 主库写，从库读
- **分区表**: 按时间分区大表

### 11.2 缓存策略

```python
from functools import lru_cache
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

@lru_cache(maxsize=1000)
def get_wind_statistics_cached(gid: int, hub_height: int) -> dict:
    """缓存风能统计结果"""
    cache_key = f"wind_stats:{gid}:{hub_height}"
    
    # 尝试从 Redis 获取
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # 计算并缓存
    result = calculate_wind_statistics(gid, hub_height)
    redis_client.setex(cache_key, 3600, json.dumps(result))  # 1小时过期
    
    return result
```

### 11.3 并行计算优化

```python
import dask.array as da
from dask.distributed import Client

# 创建 Dask 集群
client = Client(n_workers=8, threads_per_worker=2)

# 并行处理大规模数组
wind_data = da.from_array(large_wind_array, chunks=(1000, 100))
result = wind_data.mean(axis=0).compute()
```

### 11.4 内存优化

- **分块处理**: HDF5 分块读取
- **延迟加载**: 按需加载大数据集
- **垃圾回收**: 定期调用 `gc.collect()`
- **对象池**: 复用大型对象

---

## 12. 项目实施计划

### 12.1 开发阶段划分

#### 第一阶段：基础架构搭建（4周）
- Week 1-2: 环境搭建、数据库设计、用户服务开发
- Week 3-4: 项目管理服务、任务队列集成

#### 第二阶段：核心功能开发（8周）
- Week 5-6: 资源评估服务
- Week 7-8: 排除分析服务
- Week 9-10: 供应曲线聚合服务
- Week 11-12: Bespoke 优化服务

#### 第三阶段：辅助功能开发（4周）
- Week 13-14: 经济分析服务、可视化服务
- Week 15-16: API 网关、前端界面

#### 第四阶段：测试与优化（4周）
- Week 17-18: 单元测试、集成测试
- Week 19-20: 性能优化、安全加固

#### 第五阶段：部署与上线（2周）
- Week 21: 生产环境部署
- Week 22: 用户培训、文档完善

### 12.2 里程碑

| 里程碑 | 时间节点 | 交付物 |
|--------|---------|--------|
| M1: 架构完成 | Week 4 | 系统架构文档、基础服务 |
| M2: 核心功能完成 | Week 12 | 所有计算服务、API |
| M3: Beta 版本 | Week 16 | 完整系统、前端界面 |
| M4: RC 版本 | Week 20 | 测试报告、性能优化 |
| M5: 正式发布 | Week 22 | 生产系统、用户手册 |

### 12.3 风险管理

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 性能不达标 | 中 | 高 | 早期性能测试，预留优化时间 |
| 数据质量问题 | 高 | 中 | 数据验证机制，异常处理 |
| 第三方依赖变更 | 低 | 中 | 版本锁定，抽象层隔离 |
| 人员流动 | 中 | 高 | 文档完善，代码审查 |

---

## 附录

### A. 参考文献

1. NREL reV Technical Report: https://www.nrel.gov/docs/fy19osti/73067.pdf
2. reV GitHub Repository: https://github.com/NatLabRockies/reV
3. SAM Documentation: https://sam.nrel.gov/
4. FastAPI Documentation: https://fastapi.tiangolo.com/

### B. 术语表

- **GID**: Grid ID，网格单元标识符
- **SC Point**: Supply Curve Point，供应曲线点
- **LCOE**: Levelized Cost of Energy，平准化能源成本
- **AEP**: Annual Energy Production，年发电量
- **BOS**: Balance of System，系统平衡成本

### C. reV 后端开发实战指南

详细的 reV 后端开发指南已单独成文档，请参考：
- **文档位置**: `reV后端开发实战指南.md`
- **内容包括**:
  - reV 环境搭建和依赖管理
  - 核心模块集成（资源加载、排除分析、供应曲线聚合、Bespoke优化）
  - Celery 异步任务集成
  - 性能优化最佳实践
  - 错误处理和日志记录
  - 测试和调试
  - Docker/Kubernetes 部署

### D. 联系方式

技术支持邮箱: support@rev-wind-siting.com
项目管理系统: https://jira.rev-wind-siting.com
代码仓库: https://gitlab.rev-wind-siting.com

---

**文档结束**
