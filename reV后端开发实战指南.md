# reV 后端开发实战指南

## 目录

- [A.1 reV 环境搭建](#a1-rev-环境搭建)
- [A.2 reV 核心模块集成](#a2-rev-核心模块集成)
- [A.3 Celery 异步任务集成](#a3-celery-异步任务集成)
- [A.4 性能优化最佳实践](#a4-性能优化最佳实践)
- [A.5 错误处理和日志记录](#a5-错误处理和日志记录)
- [A.6 测试和调试](#a6-测试和调试)
- [A.7 部署和运维](#a7-部署和运维)

---

## A.1 reV 环境搭建

### A.1.1 Python 环境配置

```bash
# 创建虚拟环境
python -m venv rev-env
source rev-env/bin/activate  # Linux/Mac
# 或
rev-env\Scripts\activate  # Windows

# 安装 reV 及其依赖
pip install NLR-reV==0.14.5

# 安装额外依赖（用于 HSDS）
pip install NLR-reV[hsds]

# 验证安装
python -c "import reV; print(reV.__version__)"
```

### A.1.2 依赖包管理

创建 `requirements.txt`:

```txt
# 核心依赖
NLR-reV==0.14.5
NREL-PySAM==4.0.0
rex>=0.6.0
NREL-gaps>=0.7.0

# Web 框架
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.0

# 异步任务
celery==5.3.6
redis==5.0.1

# 数据库
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
alembic==1.13.0

# 地理空间处理
geopandas==0.14.2
shapely==2.0.2
rasterio==1.3.9

# 数据处理
numpy==1.26.2
pandas==2.1.4
scipy==1.11.4
dask[distributed]==2023.12.1

# 可视化
matplotlib==3.8.2
plotly==5.18.0

# 工具库
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
minio==7.2.0
```

### A.1.3 系统依赖安装

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libhdf5-dev \
    hdf5-tools \
    build-essential

# 设置 GDAL 环境变量
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal
```

---

## A.2 reV 核心模块集成

### A.2.1 资源数据加载器

```python
"""
reV 资源数据加载服务
演示如何使用 rex 和 reV 加载和处理风能资源数据
"""
from typing import List, Dict, Optional
import numpy as np
import pandas as pd
from pathlib import Path
from rex.multi_year_resource import MultiYearWindResource
from rex.resource import Resource

class WindResourceLoader:
    """风能资源数据加载器"""
    
    def __init__(self, resource_files: List[str], hsds: bool = False):
        """
        初始化资源加载器
        
        Args:
            resource_files: 资源文件路径列表，支持通配符
            hsds: 是否使用 HSDS (HDF5 Services)
        """
        self.resource_files = resource_files
        self.hsds = hsds
        self._handler = None
    
    def __enter__(self):
        """上下文管理器入口"""
        self._handler = MultiYearWindResource(
            self.resource_files, 
            hsds=self.hsds
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if self._handler:
            self._handler.close()
    
    def get_wind_speeds(self, gids: List[int], hub_height: int = 100,
                       slice_obj: slice = None) -> np.ndarray:
        """
        获取风速数据
        
        Args:
            gids: 网格 ID 列表
            hub_height: 轮毂高度（米）
            slice_obj: 时间切片，默认全部
        
        Returns:
            风速数组 (time, space)
        """
        dset_name = f'windspeed_{hub_height}m'
        
        if slice_obj is None:
            data = self._handler[dset_name, :, gids]
        else:
            data = self._handler[dset_name, slice_obj, gids]
        
        return data
    
    def get_wind_directions(self, gids: List[int], hub_height: int = 100,
                           slice_obj: slice = None) -> np.ndarray:
        """获取风向数据"""
        dset_name = f'winddirection_{hub_height}m'
        
        if slice_obj is None:
            data = self._handler[dset_name, :, gids]
        else:
            data = self._handler[dset_name, slice_obj, gids]
        
        return data
    
    def calculate_wind_statistics(self, gids: List[int], 
                                 hub_height: int = 100) -> Dict:
        """计算风能统计指标"""
        ws = self.get_wind_speeds(gids, hub_height)
        wd = self.get_wind_directions(gids, hub_height)
        
        # 基本统计
        stats = {
            'mean_wind_speed': float(np.mean(ws)),
            'std_wind_speed': float(np.std(ws)),
            'max_wind_speed': float(np.max(ws)),
            'min_wind_speed': float(np.min(ws)),
        }
        
        # 威布尔分布拟合
        from scipy.stats import weibull_min
        ws_flat = ws.flatten()
        shape, loc, scale = weibull_min.fit(ws_flat, floc=0)
        stats['weibull_scale'] = float(scale)
        stats['weibull_shape'] = float(shape)
        
        return stats


# FastAPI 端点示例
from fastapi import APIRouter

router = APIRouter()

@router.get("/resource/statistics/{gid}")
async def get_resource_statistics(gid: int, hub_height: int = 100):
    """获取单个 GID 的风能统计"""
    
    resource_files = ["/data/wtk/conus_*.h5"]
    
    with WindResourceLoader(resource_files) as loader:
        stats = loader.calculate_wind_statistics([gid], hub_height)
        
        return {
            'gid': gid,
            'hub_height': hub_height,
            'statistics': stats
        }
```

### A.2.2 排除分析服务

```python
"""
reV 排除分析服务
演示如何使用 reV 进行土地利用约束分析
"""
from typing import Dict, List, Optional
import numpy as np
from reV.handlers.exclusions import ExclusionLayers
from reV.supply_curve.exclusions import ExclusionMaskFromDict

class ExclusionAnalyzer:
    """排除分析器"""
    
    def __init__(self, exclusion_file: str, 
                 excl_dict: Dict,
                 min_area: Optional[float] = None):
        """
        初始化排除分析器
        
        Args:
            exclusion_file: 排除文件路径 (.h5)
            excl_dict: 排除配置字典
            min_area: 最小连续面积 (km²)
        """
        self.exclusion_file = exclusion_file
        self.excl_dict = excl_dict
        self.min_area = min_area
    
    def run_exclusion_analysis(self) -> Dict:
        """执行排除分析"""
        
        # 创建排除掩膜对象
        excl_mask = ExclusionMaskFromDict(
            self.exclusion_file,
            layers_dict=self.excl_dict,
            min_area=self.min_area,
            kernel='queen'
        )
        
        try:
            # 获取最终掩膜
            mask = excl_mask.mask
            
            # 计算统计信息
            total_pixels = mask.size
            included_pixels = int(np.sum(mask))
            excluded_pixels = total_pixels - included_pixels
            
            # 获取像素面积
            pixel_area_km2 = self._get_pixel_area(excl_mask)
            
            # 计算面积
            available_area = included_pixels * pixel_area_km2
            excluded_area = excluded_pixels * pixel_area_km2
            
            return {
                'available_area_km2': float(available_area),
                'excluded_area_km2': float(excluded_area),
                'inclusion_percentage': float(included_pixels / total_pixels * 100),
                'resolution': excl_mask.shape
            }
        finally:
            excl_mask.close()
    
    def _get_pixel_area(self, excl_mask) -> float:
        """计算单个像素的面积 (km²)"""
        if hasattr(excl_mask, 'transform'):
            transform = excl_mask.transform
            res_x = abs(transform[0])
            res_y = abs(transform[4])
            return (res_x * res_y) / 1e6
        else:
            return 0.0081  # 默认值


# FastAPI 端点
@router.post("/exclusion/analyze")
async def analyze_exclusions(
    exclusion_file: str,
    exclusion_config: Dict,
    min_area: Optional[float] = None
):
    """排除分析 API 端点"""
    
    analyzer = ExclusionAnalyzer(
        exclusion_file=exclusion_file,
        excl_dict=exclusion_config,
        min_area=min_area
    )
    
    result = analyzer.run_exclusion_analysis()
    
    return result
```

### A.2.3 供应曲线聚合服务

```python
"""
reV 供应曲线聚合服务
"""
from typing import List, Optional, Dict
import pandas as pd
from reV.supply_curve.aggregation import Aggregation

class SupplyCurveAggregator:
    """供应曲线聚合器"""
    
    def __init__(self, 
                 excl_fpath: str,
                 res_fpath: str,
                 tm_dset: str,
                 resolution: int = 64):
        """
        初始化供应曲线聚合器
        
        Args:
            excl_fpath: 排除文件路径
            res_fpath: 资源文件路径（支持通配符）
            tm_dset: 技术映射数据集名称
            resolution: 供应曲线点分辨率
        """
        self.excl_fpath = excl_fpath
        self.res_fpath = res_fpath
        self.tm_dset = tm_dset
        self.resolution = resolution
    
    def run_aggregation(self, 
                       gids: Optional[List[int]] = None,
                       output_request: tuple = ('cf_mean', 'lcoe')) -> pd.DataFrame:
        """
        执行供应曲线聚合
        
        Returns:
            包含聚合结果的 DataFrame
        """
        # 创建聚合器
        agg = Aggregation(
            excl_fpath=self.excl_fpath,
            tm_dset=self.tm_dset,
            res_fpath=self.res_fpath,
            resolution=self.resolution,
            gids=gids,
            output_request=output_request
        )
        
        try:
            results = []
            
            for sc_point in agg.supply_curve_points:
                try:
                    result = {
                        'sc_gid': int(sc_point.gid),
                        'latitude': float(sc_point.latitude),
                        'longitude': float(sc_point.longitude),
                        'available_area_km2': float(sc_point.available_area),
                        'cf_mean': float(sc_point.cf_mean),
                        'lcoe_real': float(sc_point.lcoe_real),
                        'capacity_ac_mw': float(sc_point.capacity_ac_mw),
                    }
                    results.append(result)
                except Exception as e:
                    logger.warning(f"Failed SC point {sc_point.gid}: {e}")
                    continue
            
            return pd.DataFrame(results) if results else pd.DataFrame()
                
        finally:
            agg.close()
    
    def export_to_csv(self, results: pd.DataFrame, output_path: str):
        """导出结果为 CSV"""
        results.to_csv(output_path, index=False)


# FastAPI 后台任务
from fastapi import BackgroundTasks

@router.post("/supply-curve/aggregate")
async def start_aggregation(
    project_id: str,
    background_tasks: BackgroundTasks,
    resolution: int = 64
):
    """启动供应曲线聚合任务"""
    
    task_id = generate_task_id()
    
    background_tasks.add_task(
        run_aggregation_task,
        task_id=task_id,
        project_id=project_id,
        resolution=resolution
    )
    
    return {'task_id': task_id, 'status': 'pending'}


async def run_aggregation_task(task_id: str, project_id: str, resolution: int):
    """后台运行聚合任务"""
    
    update_task_status(task_id, 'running')
    
    try:
        project = get_project(project_id)
        
        aggregator = SupplyCurveAggregator(
            excl_fpath=project.config['exclusion_files'][0],
            res_fpath=project.config['resource_files'][0],
            tm_dset=project.config['techmap_dataset'],
            resolution=resolution
        )
        
        results = aggregator.run_aggregation()
        
        # 保存结果
        output_path = f"/data/results/{task_id}/results.csv"
        aggregator.export_to_csv(results, output_path)
        
        update_task_status(task_id, 'completed', result_path=output_path)
        
    except Exception as e:
        logger.error(f"Aggregation failed: {e}")
        update_task_status(task_id, 'failed', error_message=str(e))
```

### A.2.4 Bespoke 优化服务

```python
"""
reV Bespoke 优化服务
"""
from typing import Dict, List
from reV.bespoke.bespoke import BespokeSinglePlant

class BespokeOptimizer:
    """Bespoke 风电场优化器"""
    
    def __init__(self, 
                 excl_fpath: str,
                 res_fpath: str,
                 tm_dset: str,
                 sam_sys_inputs: Dict):
        self.excl_fpath = excl_fpath
        self.res_fpath = res_fpath
        self.tm_dset = tm_dset
        self.sam_sys_inputs = sam_sys_inputs
    
    def optimize_single_plant(self,
                             sc_gid: int,
                             objective_function: str,
                             capital_cost_function: str,
                             ga_kwargs: Dict = None) -> Dict:
        """
        优化单个风电场布局
        
        Returns:
            优化结果字典
        """
        if ga_kwargs is None:
            ga_kwargs = {'max_time': 3600}  # 1 小时超时
        
        try:
            # 创建 BespokeSinglePlant 实例
            bsp = BespokeSinglePlant(
                gid=sc_gid,
                excl=self.excl_fpath,
                res=self.res_fpath,
                tm_dset=self.tm_dset,
                sam_sys_inputs=self.sam_sys_inputs,
                objective_function=objective_function,
                capital_cost_function=capital_cost_function,
                fixed_operating_cost_function="0",
                variable_operating_cost_function="0",
                balance_of_system_cost_function="0",
                min_spacing='5x',
                ga_kwargs=ga_kwargs,
                output_request=('system_capacity', 'cf_mean')
            )
            
            # 运行优化
            results = bsp.run_plant_optimization()
            
            # 提取结果
            optimized_results = {
                'sc_gid': int(sc_gid),
                'success': True,
                'n_turbines': int(results.get('n_turbines', 0)),
                'system_capacity_mw': float(results.get('system_capacity', 0)) / 1000,
                'bespoke_aep_kwh': float(results.get('bespoke_aep', 0)),
                'bespoke_cf_mean': float(results.get('bespoke_cf_mean', 0)),
                'capital_cost': float(results.get('capital_cost', 0)),
                'turbine_x_coords': results.get('turbine_x_coords', []),
                'turbine_y_coords': results.get('turbine_y_coords', []),
            }
            
            bsp.close()
            
            return optimized_results
            
        except Exception as e:
            logger.error(f"Optimization failed for GID {sc_gid}: {e}")
            return {
                'sc_gid': int(sc_gid),
                'success': False,
                'error': str(e)
            }


# 常用的目标函数模板
OBJECTIVE_FUNCTIONS = {
    'min_lcoe': '(fixed_charge_rate * capital_cost + fixed_operating_cost) / aep',
    'min_capital_per_mw': 'capital_cost / system_capacity',
}

COST_FUNCTIONS = {
    'capital_simple': '200 * system_capacity',
    'capital_economy': '200 * system_capacity * exp(-system_capacity / 1E5 * 0.1)',
}
```

---

## A.3 Celery 异步任务集成

### A.3.1 Celery 配置

```python
"""celery_app.py"""
from celery import Celery
import os

celery_app = Celery(
    'rev_tasks',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/1')
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_retry_backoff=True,
    task_max_retries=3,
)
```

### A.3.2 定义异步任务

```python
"""tasks.py"""
from .celery_app import celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def aggregate_supply_curve(self, project_id: str, resolution: int = 64):
    """供应曲线聚合异步任务"""
    
    task_id = self.request.id
    
    try:
        logger.info(f"Starting aggregation for project {project_id}")
        
        # 更新进度
        self.update_state(state='PROGRESS', meta={'progress': 10})
        
        # 获取项目配置
        project = get_project_from_db(project_id)
        
        # 创建聚合器
        aggregator = SupplyCurveAggregator(
            excl_fpath=project.config['exclusion_files'][0],
            res_fpath=project.config['resource_files'][0],
            tm_dset=project.config['techmap_dataset'],
            resolution=resolution
        )
        
        self.update_state(state='PROGRESS', meta={'progress': 30})
        
        # 运行聚合
        results = aggregator.run_aggregation()
        
        self.update_state(state='PROGRESS', meta={'progress': 80})
        
        # 保存结果
        output_path = save_results(results, project_id, task_id)
        
        return {
            'status': 'completed',
            'output_path': output_path,
            'n_points': len(results)
        }
        
    except Exception as exc:
        logger.error(f"Aggregation failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True)
def optimize_bespoke_plant(self, project_id: str, sc_gid: int,
                          objective_function: str):
    """Bespoke 优化异步任务"""
    
    try:
        project = get_project_from_db(project_id)
        
        optimizer = BespokeOptimizer(
            excl_fpath=project.config['exclusion_files'][0],
            res_fpath=project.config['resource_files'][0],
            tm_dset=project.config['techmap_dataset'],
            sam_sys_inputs=project.config['sam_config']
        )
        
        result = optimizer.optimize_single_plant(
            sc_gid=sc_gid,
            objective_function=objective_function,
            capital_cost_function=COST_FUNCTIONS['capital_economy']
        )
        
        # 保存结果
        save_result_to_db(result)
        
        return result
        
    except Exception as exc:
        logger.error(f"Optimization failed: {exc}")
        raise self.retry(exc=exc, countdown=120)
```

### A.3.3 任务监控 API

```python
"""task_monitor.py"""
from fastapi import APIRouter
from celery.result import AsyncResult
from .celery_app import celery_app

router = APIRouter()


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        'task_id': task_id,
        'status': result.status,
    }
    
    if result.status == 'PROGRESS':
        response['progress'] = result.info.get('progress', 0)
    elif result.status == 'SUCCESS':
        response['result'] = result.result
    elif result.status == 'FAILED':
        response['error'] = str(result.result)
    
    return response


@router.post("/tasks/{task_id}/revoke")
async def revoke_task(task_id: str):
    """撤销任务"""
    celery_app.control.revoke(task_id, terminate=True)
    return {'message': f'Task {task_id} revoked'}
```

---

## A.4 性能优化最佳实践

### A.4.1 内存管理

```python
"""memory_manager.py"""
import gc
import psutil
import logging

logger = logging.getLogger(__name__)


class MemoryManager:
    """内存管理器"""
    
    @staticmethod
    def check_memory_usage(threshold_gb: float = 8.0) -> bool:
        """检查内存使用情况"""
        process = psutil.Process()
        memory_gb = process.memory_info().rss / 1e9
        
        if memory_gb > threshold_gb:
            logger.warning(f"High memory usage: {memory_gb:.2f} GB")
            return False
        
        return True
    
    @staticmethod
    def force_garbage_collection():
        """强制垃圾回收"""
        gc.collect()
        logger.debug("Garbage collection performed")


# 使用示例
def process_large_dataset(data_loader):
    """处理大数据集时分块进行"""
    results = []
    
    for chunk in data_loader.get_chunks(chunk_size=1000):
        result = process_chunk(chunk)
        results.append(result)
        
        # 定期检查内存
        if not MemoryManager.check_memory_usage():
            MemoryManager.force_garbage_collection()
    
    return results
```

### A.4.2 并行处理优化

```python
"""parallel_processor.py"""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing


def get_optimal_n_workers(task_type: str = 'cpu_bound') -> int:
    """获取最优工作进程数"""
    cpu_count = multiprocessing.cpu_count()
    
    if task_type == 'cpu_bound':
        return max(1, cpu_count - 1)  # CPU 密集型
    else:
        return cpu_count * 2  # I/O 密集型


class ParallelProcessor:
    """并行处理器"""
    
    def __init__(self, n_workers: int = None, task_type: str = 'cpu_bound'):
        if n_workers is None:
            n_workers = get_optimal_n_workers(task_type)
        
        self.n_workers = n_workers
        self.executor_class = (
            ProcessPoolExecutor if task_type == 'cpu_bound'
            else ThreadPoolExecutor
        )
    
    def process(self, items: list, process_func: callable) -> list:
        """并行处理项目列表"""
        results = []
        
        with self.executor_class(max_workers=self.n_workers) as executor:
            futures = [executor.submit(process_func, item) for item in items]
            
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Processing failed: {e}")
                    results.append(None)
        
        return results
```

### A.4.3 缓存策略

```python
"""cache.py"""
import redis
import pickle
from functools import wraps

redis_client = redis.Redis(host='localhost', port=6379, db=0)


def cache_result(key_prefix: str, ttl: int = 3600):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args))}"
            
            # 尝试从缓存获取
            cached = redis_client.get(cache_key)
            if cached:
                return pickle.loads(cached)
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            redis_client.setex(cache_key, ttl, pickle.dumps(result))
            
            return result
        return wrapper
    return decorator


# 使用示例
@cache_result(key_prefix='wind_stats', ttl=7200)
def get_wind_statistics_cached(gid: int, hub_height: int):
    """获取风能统计（带缓存）"""
    return calculate_wind_statistics(gid, hub_height)
```

---

## A.5 错误处理和日志记录

### A.5.1 统一异常处理

```python
"""exceptions.py"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


class ReVBaseException(Exception):
    """reV 基础异常类"""
    def __init__(self, message: str, code: str = "REV_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ResourceDataError(ReVBaseException):
    """资源数据错误"""
    def __init__(self, message: str):
        super().__init__(message, "RESOURCE_DATA_ERROR")


class ExclusionAnalysisError(ReVBaseException):
    """排除分析错误"""
    def __init__(self, message: str):
        super().__init__(message, "EXCLUSION_ANALYSIS_ERROR")


class OptimizationError(ReVBaseException):
    """优化错误"""
    def __init__(self, message: str):
        super().__init__(message, "OPTIMIZATION_ERROR")


def register_exception_handlers(app: FastAPI):
    """注册异常处理器"""
    
    @app.exception_handler(ReVBaseException)
    async def rev_exception_handler(request: Request, exc: ReVBaseException):
        logger.error(f"reV Error [{exc.code}]: {exc.message}")
        
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.code,
                "message": exc.message,
                "path": request.url.path
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "path": request.url.path
            }
        )


# 在 main.py 中注册
app = FastAPI()
register_exception_handlers(app)
```

### A.5.2 结构化日志

```python
"""logging_config.py"""
import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO"):
    """设置结构化日志"""
    
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # JSON 格式化器
    log_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(formatter)
    
    logger.addHandler(log_handler)
    
    return logger


# 使用示例
logger = setup_logging("INFO")

logger.info("Starting aggregation", extra={
    'project_id': '12345',
    'resolution': 64
})

logger.error("Aggregation failed", extra={
    'project_id': '12345',
    'error': str(exc)
})
```

---

## A.6 测试和调试

### A.6.1 单元测试

```python
"""test_resource_loader.py"""
import pytest
import numpy as np
from src.services.wind_resource import WindResourceLoader


class TestWindResourceLoader:
    """风能资源加载器测试"""
    
    @pytest.fixture
    def resource_loader(self):
        """创建测试用的资源加载器"""
        return WindResourceLoader(
            resource_files=["/test/data/wtk_test.h5"],
            hsds=False
        )
    
    def test_get_wind_speeds(self, resource_loader):
        """测试获取风速数据"""
        with resource_loader:
            speeds = resource_loader.get_wind_speeds(
                gids=[0, 1, 2],
                hub_height=100
            )
            
            assert isinstance(speeds, np.ndarray)
            assert speeds.shape[1] == 3  # 3个GID
            assert not np.isnan(speeds).any()
    
    def test_calculate_statistics(self, resource_loader):
        """测试统计计算"""
        with resource_loader:
            stats = resource_loader.calculate_wind_statistics(
                gids=[0],
                hub_height=100
            )
            
            assert 'mean_wind_speed' in stats
            assert 'weibull_scale' in stats
            assert stats['mean_wind_speed'] > 0


# 运行测试
# pytest tests/test_resource_loader.py -v
```

### A.6.2 集成测试

```python
"""test_api_integration.py"""
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_exclusion_analysis_endpoint():
    """测试排除分析端点"""
    
    payload = {
        "exclusion_file": "/test/data/exclusions.h5",
        "exclusion_config": {
            "slope": {"inclusion_range": [None, 5]},
            "protected": {"exclude_values": [1]}
        },
        "min_area": 1.0
    }
    
    response = client.post("/api/v1/exclusion/analyze", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert 'available_area_km2' in data
    assert 'excluded_area_km2' in data
    assert data['available_area_km2'] >= 0


def test_task_status_endpoint():
    """测试任务状态查询"""
    
    # 提交任务
    submit_response = client.post(
        "/api/v1/supply-curve/aggregate",
        json={"project_id": "test-project"}
    )
    
    task_id = submit_response.json()['task_id']
    
    # 查询状态
    status_response = client.get(f"/api/v1/tasks/{task_id}")
    
    assert status_response.status_code == 200
    assert 'status' in status_response.json()
```

### A.6.3 性能基准测试

```python
"""benchmark_aggregation.py"""
import time
import pytest
from src.services.supply_curve import SupplyCurveAggregator


def benchmark_aggregation_performance():
    """基准测试：聚合性能"""
    
    aggregator = SupplyCurveAggregator(
        excl_fpath="/data/exclusions.h5",
        res_fpath="/data/wtk_conus.h5",
        tm_dset="techmap_wtk",
        resolution=64
    )
    
    # 预热
    aggregator.run_aggregation(gids=list(range(10)))
    
    # 正式测试
    start_time = time.time()
    results = aggregator.run_aggregation(gids=list(range(100)))
    elapsed = time.time() - start_time
    
    print(f"\nProcessed 100 SC points in {elapsed:.2f} seconds")
    print(f"Average: {elapsed/100:.3f} seconds per point")
    
    assert elapsed < 300  # 应该在 5 分钟内完成
```

---

## A.7 部署和运维

### A.7.1 Docker Compose 配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Redis - 消息代理和缓存
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  # PostgreSQL - 元数据存储
  postgres:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: rev_wind_siting
      POSTGRES_USER: rev_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # MinIO - 对象存储
  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: ${MINIO_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

  # FastAPI 应用
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
      DB_URL: postgresql://rev_admin:${DB_PASSWORD}@postgres:5432/rev_wind_siting
      MINIO_ENDPOINT: minio:9000
    depends_on:
      - redis
      - postgres
      - minio
    volumes:
      - ./data:/data

  # Celery Worker - 计算任务
  celery_worker:
    build: .
    command: celery -A src.tasks.celery_app worker --loglevel=info -Q supply_curve,bespoke,exclusion
    environment:
      REDIS_URL: redis://redis:6379/0
      DB_URL: postgresql://rev_admin:${DB_PASSWORD}@postgres:5432/rev_wind_siting
    depends_on:
      - redis
      - postgres
    volumes:
      - ./data:/data
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 8G
          cpus: '4'

  # Celery Beat - 定时任务
  celery_beat:
    build: .
    command: celery -A src.tasks.celery_app beat --loglevel=info
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - redis

volumes:
  redis_data:
  postgres_data:
  minio_data:
```

### A.7.2 Kubernetes 部署

```yaml
# k8s/celery-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
      - name: worker
        image: rev/wind-siting:latest
        command: ["celery"]
        args: [
          "-A", "src.tasks.celery_app", "worker",
          "--loglevel=info",
          "-Q", "supply_curve,bespoke,exclusion"
        ]
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: DB_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: database-url
        volumeMounts:
        - name: data-volume
          mountPath: /data
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: data-pvc
```

### A.7.3 监控和告警

```python
"""monitoring.py"""
from prometheus_client import Counter, Histogram, Gauge
import time

# Prometheus 指标
TASK_COUNTER = Counter(
    'rev_tasks_total',
    'Total number of tasks',
    ['task_type', 'status']
)

TASK_DURATION = Histogram(
    'rev_task_duration_seconds',
    'Task duration in seconds',
    ['task_type']
)

ACTIVE_TASKS = Gauge(
    'rev_active_tasks',
    'Number of active tasks'
)


class TaskMonitor:
    """任务监控器"""
    
    def __init__(self, task_type: str):
        self.task_type = task_type
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        ACTIVE_TASKS.inc()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        ACTIVE_TASKS.dec()
        
        TASK_DURATION.labels(task_type=self.task_type).observe(duration)
        
        if exc_type is None:
            TASK_COUNTER.labels(
                task_type=self.task_type,
                status='success'
            ).inc()
        else:
            TASK_COUNTER.labels(
                task_type=self.task_type,
                status='failure'
            ).inc()


# 使用示例
def run_aggregation_task(project_id: str):
    with TaskMonitor('supply_curve_aggregation'):
        # 执行聚合
        results = aggregator.run_aggregation()
        return results
```

### A.7.4 日志聚合

```yaml
# docker-compose.logging.yml
version: '3.8'

services:
  # Elasticsearch
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"

  # Kibana
  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch

  # Fluentd - 日志收集
  fluentd:
    image: fluent/fluentd:v1.16
    volumes:
      - ./fluentd/conf:/fluentd/etc
    ports:
      - "24224:24224"
    depends_on:
      - elasticsearch

volumes:
  es_data:
```

---

## 总结

本指南详细介绍了如何基于 reV 进行后端开发，包括：

1. **环境搭建**：Python 环境、依赖管理、系统依赖
2. **核心模块集成**：资源加载、排除分析、供应曲线聚合、Bespoke 优化
3. **异步任务**：Celery 配置、任务定义、监控
4. **性能优化**：内存管理、并行处理、缓存策略
5. **错误处理**：统一异常处理、结构化日志
6. **测试**：单元测试、集成测试、性能基准测试
7. **部署运维**：Docker、Kubernetes、监控告警

通过这些实践，开发者可以构建高性能、可扩展的风电场宏观选址系统。
