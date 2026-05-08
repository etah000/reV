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
- `exclusions_techmap.py` — 生成占位排除栅格与 techmap（KD-tree 映射）。
- `config_generator.py` — 生成 reV 所需的 JSON 配置文件与 SAM 风机配置、输电表。
- `download_era5.py` — 使用 CDS API 下载 ERA5 数据的辅助脚本（需配置 `~/.cdsapirc`）。
- `build_beijing_dataset.py` — 顶层 CLI，按步骤执行全部流程（网格→气象→写 HDF5→project_points→exclusions→配置）。

## 快速开始（示例）

1. 安装依赖（推荐在 `rev` conda 环境中）：

```bash
pip install xarray netcdf4 cfgrib cdsapi geopandas scipy
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
  --overwrite
```

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

---

如需我把 README 转为中文/英文双语、加入示例截图或把 README 的使用命令整理为 Makefile，我可以继续补充。