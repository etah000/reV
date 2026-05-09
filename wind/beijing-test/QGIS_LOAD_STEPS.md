# QGIS 展示步骤（对应 reV-RPM Overview 11/12/13 页风格）

## 0. 数据来源
- 图层包：`qgis_layers.gpkg`
- 图片：`fig_*.png`
- TOP5 摘要：`top5_points_summary.csv`

## 1. 第12页风格：网格化风资源图（project points + 合成资源）
1. 在 QGIS 中添加图层：`qgis_layers.gpkg|layername=grid_resource`。
2. 样式：`Graduated`，字段选 `annual_energy_mwh`，色带推荐 `YlGnBu`。
3. 叠加 `qgis_layers.gpkg|layername=top5_points`，点样式红色圆点（或叉号）。
4. 布局中插入标题：`Beijing wind grid annual energy`。

## 2. 第11页风格：TOP5 发电图（折线 + 柱状）
- 日尺度折线图：`fig_11_top5_daily_energy_line.png`
- 周尺度折线图：`fig_11_top5_weekly_energy_line.png`
- 柱状图文件：`fig_11_top5_annual_energy_bar.png`
- 数据表：`top5_points_summary.csv`

说明：
- 年发电量由 `cf_mean × system_capacity × 8760` 计算得到（单位 MWh）。
- 曲线将年电量按每小时 `windspeed^3` 权重分配后再聚合：
	- 日尺度用于保留季节性细节。
	- 周尺度用于更平滑地比较不同 `gid`。

## 3. 第13页风格：叠加排除区域
1. 加载 `qgis_layers.gpkg|layername=grid_resource`（底图）。
2. 加载 `qgis_layers.gpkg|layername=exclusions_points`（排除像元）。
3. 将 `exclusions_points` 设为红色小点、40~50% 透明度。
4. 可再叠加 `top5_points` 突出高发电格点。

## 4. 最终供应曲线图
- 直接使用：`fig_supply_curve.png`
- 曲线定义：按成本字段升序排序（优先 `lcoe_all_in_usd_per_mwh`，若缺失回退到 `lcoe_site_usd_per_mwh + lcot_usd_per_mwh`，再回退 `lcot_usd_per_mwh`），横轴为累积 `capacity_ac_mw`。

## 5. 已生成文件清单
- `qgis_layers.gpkg`
- `fig_12_grid_resource_map.png`
- `fig_11_top5_daily_energy_line.png`
- `fig_11_top5_weekly_energy_line.png`
- `fig_11_top5_annual_energy_bar.png`
- `fig_13_exclusions_overlay_map.png`
- `fig_supply_curve.png`
- `top5_points_summary.csv`
