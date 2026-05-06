# local_wind_pipeline_ri_final 图示（QGIS）

本目录中的图和图层文件可直接在 QGIS 里复现类似 reV-RPM Overview 第 11/12/13 页与供应曲线图的效果。

## 1. 数据位置

- 资源网格面: `qgis_layers/resource_grid.geojson`
- project points 点图层: `qgis_layers/project_points.geojson`
- 供应曲线网格面: `qgis_layers/supply_curve_cells.geojson`
- 供应曲线属性表: `qgis_layers/supply_curve_cells.csv`
- 现成导出图: 
  - `resource_project_points_map.png`
  - `top5_generation_profiles.png`
  - `exclusion_overlay_map.png`
  - `supply_curve.png`

## 2. QGIS 加载顺序（建议）

1. 加载 `resource_grid.geojson` 作为底图层。
2. 加载 `project_points.geojson` 叠加在上方。
3. 加载 `supply_curve_cells.geojson` 用于排除区/可开发比例展示。

## 3. 样式建议（对应 PPT）

- 第12页风资源+项目点网格图
  - `resource_grid`：单色浅灰填充，细白边。
  - `project_points`：按 `cf_mean` 渐变色（YlGnBu），点边框深色。
  - 可用规则渲染高亮 top5：表达式 `array_contains(array(<gid1>,<gid2>,<gid3>,<gid4>,<gid5>), "gid")`。

- 第13页排除区叠加图
  - `supply_curve_cells`：按 `developable_ratio` 渐变（YlOrRd）。
  - 透明度建议 30%~45%，并在下方保留 `resource_grid`。

- 供应曲线图
  - 使用 `supply_curve.png`（脚本已生成），或在 QGIS Data Plotly 里用：
    - X: cumulative capacity (MW)
    - Y: `lcoe_all_in_usd_per_mwh`

## 4. 折线+柱状图说明（第11页风格）

`top5_generation_profiles.png` 已按“小时级”生成：

- 折线：Top5 格点 8760 小时发电曲线（UTC）
- 柱状：Top5 格点全年总发电量（MWh）

## 5. 重生成命令（rev 环境）

在本目录执行：

```bash
conda run -n rev python make_visuals.py
```
