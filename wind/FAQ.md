# 风电技术分析常见术语 FAQ

---

## Q1: 什么是 Capacity Factor（容量因子）？

**Capacity Factor（容量因子）** 是指一个发电设施在一段时间内**实际发电量**与其**理论最大发电量**（满负荷连续运行）的比值，通常以百分比或小数表示。

$$CF = \frac{\text{实际发电量（MWh）}}{\text{装机容量（MW）} \times \text{时间（h）}}$$

**示例：** 一台 2MW 风机，一年实际发电 5,256 MWh，则：
$$CF = \frac{5256}{2 \times 8760} \approx 0.30 = 30\%$$

在 reV 中，capacity factor 是 generation 模块对每个站点（grid cell）运行 SAM 仿真后输出的核心结果，是衡量风/光资源质量的基础指标。

---

## Q2: 什么是 Supply Curve（供给曲线）？

**Supply Curve（供给曲线）** 是一种描述**可再生能源发电潜力与其开发成本关系**的曲线。横轴为累计可开发容量（GW），纵轴为平准化度电成本（LCOE，$/MWh）。

供给曲线的含义：
- 将所有潜在开发地点按照成本从低到高排序
- 直观展示"在某个成本上限内，最多能开发多少装机容量"
- 是政策制定、规划研究的核心工具

在 reV 中，供给曲线由 `reV/supply_curve/` 模块生成，综合了：
1. 资源质量（capacity factor）
2. 技术排除（exclusions）
3. 空间聚合（aggregation）
4. 经济成本（LCOE/econ）

---

## Q3: 什么是 Techmap（技术映射）？

**Techmap（技术映射，也称 Resource-to-Exclusion 映射）** 是将**高分辨率资源数据网格**（如 90m 风资源格点）映射到**低分辨率排除层网格**（如 90m 或更粗粒度的供给曲线聚合单元）的索引表。

具体来说：
- 资源数据（如 WTK 风资源 HDF5 文件）的每个站点（gid）对应地球上一个具体坐标
- 排除层（exclusions）是一个栅格文件（GeoTIFF），有自己的网格分辨率和投影
- techmap 记录了"每个排除层像素内包含哪些资源站点 gid"

**作用：** 在供给曲线聚合时，系统通过 techmap 知道每个聚合单元内有哪些实际的风机资源点，从而加权平均 capacity factor、统计可用面积等。

在 reV 中，techmap 由 `reV/supply_curve/tech_mapping.py` 生成，存储为 HDF5 数据集。

---

## Q4: 空间粒度的问题——90m、2km 和 12km 分别是什么？如何确定？

这三个尺度分别对应分析流程的不同阶段：

| 尺度 | 含义 | 来源 |
|------|------|------|
| **90m** | 资源数据与技术潜力评估的原始分辨率 | 风资源数据集（如 NREL WTK）的原生网格间距 |
| **~2km（实为约 2km×2km）** | 资源数据站点的实际间距 | WTK 数据集的站点网格间距约为 2km |
| **~12km（供给曲线聚合单元）** | 供给曲线聚合（SC point）的空间粒度 | 排除层栅格分辨率（通常 90m）× 聚合因子（通常 128 像素 → ~11.5km） |

### 90m 分辨率的来源

90m 是美国 NLCD（National Land Cover Database）等土地利用/排除层数据的标准分辨率。reV 的排除层分析在该分辨率下执行，以确保与土地覆盖、保护区、坡度等数据集对齐。

> "The technical potential analysis is evaluated at 90m spatial resolution"——这里的 90m 指的是排除层像素的分辨率，即每个像素代表 90m×90m 的地块，用于判断该地块是否可用于风电开发。

### 聚合到 ~12km 的原因

将 90m 像素聚合到更大的供给曲线单元（SC point）是为了：
1. **模拟电厂尺度**：一个 SC 点代表一个可开发的"离散电厂"，其面积足以容纳多台风机
2. **降低计算量**：全美有数十亿个 90m 像素，直接在该尺度做经济分析不现实
3. **与电网规划对齐**：12km 左右的尺度与输电线路规划、电网节点分析更匹配

聚合因子（resolution）是 reV `SupplyCurveAggregation` 的可配置参数，不同研究可设置不同值。

---

## Q5: Wind Scenarios 中 Open Access、Limited Access、Reference 各是什么含义？

这三个场景来自 NREL 风电技术潜力分析（如 NREL 的 ATB 或 Wind Vision 报告），代表不同的**土地可用性假设**：

| 场景 | 含义 | 排除严格程度 |
|------|------|------------|
| **Open Access（开放获取）** | 除法定保护区（国家公园、湿地、军事禁区等）外，所有土地均可用于风电开发 | 最宽松，技术潜力最大 |
| **Limited Access（有限获取）** | 在 Open Access 基础上，额外排除部分敏感区域（如森林、坡度过大区域、特定距离内的居民区等） | 中等，较为保守 |
| **Reference（参考场景）** | 基于当前政策和实际开发经验，排除大量受限土地，代表"现实可行"的开发潜力 | 最严格，最接近实际 |

**用途：** 三个场景用于敏感性分析，帮助决策者理解不同土地政策下的可再生能源潜力区间。

---

## Q6: Technical Exclusion 是按网格过滤还是按多边形排除？

**两者都有，但底层统一转换为栅格（网格）操作。**

### 工作原理

1. **输入数据多样：** 排除区域的原始数据可以是：
   - 矢量多边形（如保护区边界 Shapefile、城市建成区）
   - 栅格数据（如坡度 GeoTIFF、土地覆盖分类图）

2. **统一转换为栅格：** reV 的排除层处理（`ExclusionLayers`）将所有输入数据**光栅化（rasterize）**为统一分辨率（通常 90m）的二值栅格：
   - `1` = 该像素可用
   - `0` = 该像素被排除

3. **逐像素布尔运算：** 多个排除条件通过逻辑与（AND）/或（OR）组合，得到最终的可用性掩膜（mask）。

4. **面积统计：** 每个供给曲线聚合单元内，统计可用像素数，乘以像素面积，得到可用土地面积。

### 代码位置
- `reV/supply_curve/exclusions.py` — 排除层加载与组合
- `reV/handlers/exclusions.py` — HDF5 格式排除层文件读写

---

## Q7: Capacity Factor 是如何从站点聚合为 Technical Potential，再聚合为电厂的？

这是一个两级聚合过程：

### 第一级：资源站点 → Technical Potential（技术潜力）

1. reV generation 模块对每个资源站点（~2km 间距）运行 SAM 仿真，输出该站点的**逐小时或年均 capacity factor**
2. 在排除层分析中，90m 像素的可用性掩膜确定哪些区域可以放置风机
3. 对每个供给曲线聚合单元（~12km），统计其内部：
   - **可用面积**（90m 可用像素数 × 像素面积）
   - **加权平均 capacity factor**（以可用像素面积为权重，对覆盖该聚合单元的资源站点 CF 加权平均）
4. 用可用面积除以风机占地密度（MW/km²），乘以加权平均 CF，得到该聚合单元的**技术潜力（MWh/年）**

$$\text{Technical Potential} = \text{可用面积} \times \text{装机密度} \times \text{CF} \times 8760$$

### 第二级：聚合单元 → 离散电厂（Supply Curve Point）

1. 每个供给曲线聚合单元被视为一个"潜在电厂"
2. 其装机容量 = 可用面积 × 装机密度（MW/km²，考虑风机间距）
3. 其年发电量 = 装机容量 × CF × 8760h
4. 结合经济模型（输电成本、建设成本等）计算 LCOE
5. 所有聚合单元按 LCOE 排序，形成供给曲线

### reV 代码流程

```
generation/  →  CF (per resource site)
                    ↓
supply_curve/tech_mapping.py  →  resource site → exclusion pixel mapping
                    ↓
supply_curve/aggregation.py   →  per SC point: weighted CF, available area, capacity
                    ↓
supply_curve/sc_aggregation.py →  LCOE, supply curve table
```

---

*本文档基于 NREL reV 框架及相关风电技术潜力分析方法整理。*
