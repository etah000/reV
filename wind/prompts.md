## 在当前项目根目录下输出一个"风电场宏观选址投标书大纲.md"文档

- 编写一个用于投标的投标书中的技术可行性标书大纲，整个系统以[rev](https://github.com/NatLabRockies/reV)为基础。

## 参考材料来源

- 当前代码仓库中的文档，代码和示例
- 官方网站
- 论文："73067.pdf"
- 其他在线资源



## 可能的问题

- 数据接口不一致
- 支持路上风电场
- 计算量比较大，计算时间比较长


## 生成风电pipeline示例
### 生成
- 在当前仓库，或者其tutorial仓库”/Users/frank/opensource/reV-tutorial", 有完整pipeline流程的风电示例吗。如果有，其可以本地运行吗，其对应的示例数据（比如风资源，project points，排除等）是前后一致的吗。
- 如果没有，如何构造一个这样的示例，其测试数据大小不要太大（每个数据文件在100M以下）？

### 优化
- 移除不在需要的中间测试目录和文件
- 对于最终的测试项目：local_wind_pipeline_ri_final
  1. project points 是根据资源文件生成的，统一的使用为一个project points文件
  2. ri_exclusions_local.h5和原始的有什么区别？
  3. pipeline中的collect， multiyear都会被执行吗？
  4. 优化项目配置和代码

### 图示
使用qgis，把“local_wind_pipeline_ri_final”中的示例wind pipeline演示项目，图示出来。参考：“/Users/frank/opensource/reV-tutorial/archive/presentations/reV-RPM Overview.pptx”
- 把原始风资源文件结合project point，展示为一个网格化的地图，类似于“/第12页的地图。
- 对于每个格点上计算出的电能，输出类似于11页的折线图和柱状图，输出最高的前5个即可。
- 叠加排出区域，生成类似于13页的地图
- 图示最后的供应曲线图。

### 构造数据
以"/Users/frank/opensource/test-data/beijing/beijing.geojson"为基础，构造一个reV可以接收的风资源文件。
- 以4平方公里的大小，划分格点(grid),创建project points。使用qgis加载geojson数据，并不图示化分格结果。
- 提供合成风力、气象数据的方案，根据用户反馈，生成相应的风资源、气象数据。时间上以小时为单位，提供一整年数据。空间上以上述格点为单位，高度100m。除了风速、风向，还包括气压和温度。
- 生成相应的Python脚本文件，尽可能以函数方式分解、封装每一个功能模块，便于后期复用。

