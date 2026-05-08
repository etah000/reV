# 北京风资源测试数据集（beijing-test）

本目录包含为 reV 风资源流水线准备的脚本、适配器和示例数据；支持两种数据源模式：

- Phase-A（合成气象场）— 统计方法生成的合成风速/风向/温度/气压，用于快速开发与回归测试。
- Phase-B（ERA5 再分析）— 通过 ERA5 NetCDF4/GRIB 插值到站点，生成与 Phase-A 相同的 reV/rex 资源 HDF5 格式。

**目录（部分）**

- `grid_generation.py` — 按 GeoJSON 边界生成 2 km × 2 km 网格与站点元数据（`site_meta.csv`）。
- `synthetic_met.py` — Phase-A 合成气象数据生成器（并在 ERA5 模式下委托到 `era5_adapter.py`）。
- `era5_adapter.py` — Phase-B：读取 ERA5 NetCDF4/GRIB，空间插值并生成 4 个 reV 变量时间序列。
- `resource_writer.py` — 将元数据与时序写入 reV/rex 兼容的 HDF5，并校验结构与物理范围。
- `project_points.py` — 生成 `project_points.csv` 供 reV 生成模块使用。
- `exclusions_techmap.py` — 基于 OSM PBF 合成 exclusions（并生成 techmap，KD-tree 映射）。
- `config_generator.py` — 生成 reV 所需的 JSON 配置文件与 SAM 风机配置、输电表。
- `download_era5.py` — 使用 CDS API 下载 ERA5 数据的辅助脚本（需配置 `~/.cdsapirc`）。
- `build_beijing_dataset.py` — 顶层 CLI，按步骤执行全部流程（网格→气象→写 HDF5→project_points→exclusions→配置）。

## 快速开始（示例）

1. 安装依赖（推荐在 `rev` conda 环境中）：

```bash
pip install xarray netcdf4 cfgrib cdsapi geopandas pyogrio pyproj shapely scipy
```

2. 使用合成气象（Phase-A，默认）：

```bash
python build_beijing_dataset.py \
  --geojson /Users/frank/opensource/test-data/beijing/beijing.geojson \
  --output ./output \
  --year 2012 \
  --hub-height 100 \
  --seed 42 \
  --overwrite
```

3. 使用 ERA5（Phase-B）：先下载 ERA5 NetCDF4 或 GRIB（见下文），然后：

```bash
python build_beijing_dataset.py \
  --geojson /Users/frank/opensource/test-data/beijing/beijing.geojson \
  --output ./output_era5 \
  --year 2012 \
  --era5 ./era5_data/beijing_era5_2012.nc \
  --osm-pbf /Users/frank/opensource/test-data/beijing/beijing-260416.osm.pbf \
  --overwrite
```

## exclusions 生成原理

- 栅格构建：先将站点转到 UTM50N，按 `pixel_m` 生成规则网格，再回投到 WGS84 写入 HDF5。
- OSM 要素筛选：从 `multipolygons` 与 `lines` 图层提取约束要素。
- 面要素排除：`landuse`（居住/商业/工业等）、`natural=water|wetland`、`boundary=protected_area`、`aeroway`。
- 线要素排除：`highway`、`railway`、`aeroway` 按类型缓冲固定距离后排除。
- 栅格赋值：像元中心若落在排除几何内，则值为 `0`（excluded），否则为 `100`（included）。
- Techmap：在 UTM 米制坐标下，用 KD-tree 将每个像元映射到最近 `gid`，超阈值赋值 `-1`。

## 下载 ERA5（示例）

- 配置 CDS API：在 `~/.cdsapirc` 中添加你的 CDS key（参见 Copernicus CDS 网站说明）。
- 使用仓内脚本逐年或逐月下载：

```bash
pip install cdsapi
python download_era5.py --year 2012 --bbox 38.5/114.5/42.5/118.5 --output ./era5_data
# 或逐月：
python download_era5.py --year 2012 --monthly --output ./era5_data
```

## 冒烟测试（快速）

在没有全量 ERA5 时，可用合成 NetCDF 做冒烟测试（仓内工具已生成合成测试文件）：

```bash
# 例：生成并用合成 ERA5 运行 Phase-B 冒烟测试（脚本内部已提供 helper）
python build_beijing_dataset.py \
  --geojson /Users/frank/opensource/test-data/beijing/beijing.geojson \
  --output ./output \
  --year 2012 \
  --era5 ./output/test_era5_2012.nc \
  --smoke-test --overwrite
```

## 输出文件（示例）

- `output/beijing_wind_resource_2012.h5` — reV/rex 兼容资源 HDF5（`meta`, `time_index`, `windspeed_100m`, `winddirection_100m`, `temperature_100m`, `pressure_100m`）。
- `output/project_points.csv` — reV 项目点清单。
- `output/beijing_exclusions.h5` — 占位排除栅格与 techmap。
- `output/config_*.json`、`output/sam_wind_default.json` — reV 配置与 SAM 风机设置。

## 已知事项与实现细节

- 时间长度：2012 为闰年 → 8784 小时（UTC 时区）。
- ERA5 优先使用 `u100`/`v100`；若不存在，回退到 `u10`/`v10` 并用幂律外推到机舱高度（alpha=0.14，默认可调）。
- 温度从 `t2m`（K）转换为 °C，并对高度应用干绝热递减率修正（实现见 `era5_adapter.py`）。
- 气压从 `sp`（Pa）按气压高度公式外推到机舱高度。
- 空间插值：使用 `scipy.interpolate.RegularGridInterpolator` 做双线性插值；当 ERA5 时间分辨率不足时，使用最近邻或前后填充并发出警告。

## 运行建议

- 首次运行前，建议用 `--smoke-test` 验证流程并调试依赖。完整站点（约 4107 个）和全年小时数会显著增加内存/IO 成本。
- 若使用真实 ERA5 全年文件，建议先在小区域或逐月文件上测试，然后再合并全量文件。

## 参考：数据文件生成原理（逐项）

本节按“输入数据 / 过程产物 / 最终产物”给出每个文件的来源、算法原理和在流水线中的作用。

### 输入数据

- `beijing.geojson`
  - 来源：外部边界数据（研究区多边形）。
  - 作用：作为空间裁剪边界，决定站点网格覆盖范围。
  - 原理：`grid_generation.py` 将边界投影到 UTM，按固定网格边长做规则切分，输出落在边界内的网格中心。

- `beijing-260416.osm.pbf`
  - 来源：OpenStreetMap 北京区域 PBF。
  - 作用：合成 exclusions 栅格。
  - 原理：`exclusions_techmap.py` 从 `multipolygons` 和 `lines` 提取约束要素（建成区、水体/湿地、保护地、交通走廊缓冲区），将像元中心落入约束几何的像元置为 0（excluded），其余置为 100（included）。

- `beijing_era5_YYYY.nc` / `*.grib`
  - 来源：CDS 下载的 ERA5 单层小时数据。
  - 作用：Phase-B 气象输入。
  - 原理：`era5_adapter.py` 自动识别变量并插值到站点：
    - 风：优先 `u100/v100`，否则 `u10/v10` 后按幂律外推到机舱高度。
    - 温度：`t2m`（K）转 °C，再做机舱高度递减率修正。
    - 气压：`sp` 或 `msl` 按气压公式修正到机舱高度。

### 过程产物

- `site_meta.csv`
  - 生成脚本：`grid_generation.py`
  - 作用：所有后续步骤的站点主索引。
  - 字段原理：
    - `gid`：站点唯一编号。
    - `latitude/longitude`：网格中心回投 WGS84 坐标。
    - `elevation`：站点高程（来自地形采样逻辑）。
    - 其他行政字段用于下游可视化与审计。

- `grid_cells.geojson`
  - 生成脚本：`grid_generation.py`
  - 作用：QGIS 检查和空间核对。
  - 原理：输出每个站点对应的网格面（或中心点映射网格）并保持与 `site_meta.csv` 的 `gid` 对齐。

- `test_era5_YYYY.nc`（可选）
  - 生成脚本：`era5_adapter.py` 的测试 helper。
  - 作用：在没有真实 ERA5 时进行流程冒烟测试。
  - 原理：构造符合 ERA5 变量命名和坐标规范的合成气象场。

### 最终产物

- `beijing_wind_resource_YYYY.h5`
  - 生成脚本：`resource_writer.py`
  - 作用：reV/rex 标准资源文件，供 `reV-gen` 直接读取。
  - 结构原理：
    - `meta`：站点元数据（与 `gid` 一一对应）。
    - `time_index`：全年小时索引（闰年 8784，平年 8760）。
    - `windspeed_100m/winddirection_100m/temperature_100m/pressure_100m`：`(time, site)` 二维数组。

- `project_points.csv`
  - 生成脚本：`project_points.py`
  - 作用：定义 `reV-gen` 需要计算的项目点与配置映射。
  - 原理：最小配置下通常为 `gid -> default`，用于 SAM 参数绑定。

- `beijing_exclusions.h5`
  - 生成脚本：`exclusions_techmap.py`
  - 作用：供 `reV-supply-curve-aggregation` 使用的排除与映射文件。
  - 结构原理：
    - `latitude/longitude`：exclusions 栅格像元中心。
    - `beijing_osm_exclusions`（默认 key）：`(1, row, col)`，0=排除，100=可用。
    - `techmap_beijing`：每个像元映射到最近资源 `gid`，超阈值为 -1。

- `beijing_transmission_table.csv`
  - 生成脚本：`config_generator.py`
  - 作用：供 `reV-supply-curve` 计算并网成本。
  - 原理：提供供需节点、距离或成本参数的占位/示例传输表。

- `sam_wind_default.json`
  - 生成脚本：`config_generator.py`
  - 作用：SAM 风机与经济参数模板。
  - 原理：定义功率曲线、轮毂高度、系统容量与成本参数；由 `project_points.csv` 的 `config` 字段引用。

- `config_generation.json`
  - 生成脚本：`config_generator.py`
  - 作用：`reV-gen` 配置。
  - 原理：绑定 `resource_file`、`project_points`、`sam_files`、输出请求和并行执行参数。

- `config_sc_aggregation.json`
  - 生成脚本：`config_generator.py`
  - 作用：`reV-supply-curve-aggregation` 配置。
  - 原理：绑定 `excl_fpath`、`tm_dset`、`res_fpath`，定义分辨率和资源分箱规则。

- `config_supply_curve.json`
  - 生成脚本：`config_generator.py`
  - 作用：`reV-supply-curve` 配置。
  - 原理：读取聚合结果与输电表，计算并网后供给曲线成本字段。

- `config_pipeline.json`
  - 生成脚本：`config_generator.py`
  - 作用：一键串联 `reV-gen -> reV-supply-curve-aggregation -> reV-supply-curve`。
  - 原理：按顺序声明各模块配置文件，后续步骤可用 `PIPELINE` 引用前一步结果。

- `logs/`（目录）
  - 生成脚本：reV 各模块运行时写入。
  - 作用：诊断与审计。
  - 原理：保存模块日志、告警和异常堆栈，便于定位配置和数据问题。

### 文件一致性约束（建议核查）

- `site_meta.csv` 的 `gid` 必须与 `beijing_wind_resource_YYYY.h5/meta` 空间顺序一致。
- `beijing_exclusions.h5/techmap_beijing` 的 gid 取值必须落在资源文件 gid 范围内（或为 -1）。
- `config_generation.json` 的 `resource_file` 与 `project_points` 路径应与输出目录一致。
- `config_sc_aggregation.json` 中 `tm_dset` 名称必须与 exclusions 文件内数据集一致。

---

如需我把 README 转为中文/英文双语、加入示例截图或把 README 的使用命令整理为 Makefile，我可以继续补充。