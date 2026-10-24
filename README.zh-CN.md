# join-grain 中文说明

在真正连接 CSV 之前，预估重复键会产生多少行。使用临时 SQLite 磁盘索引，
无需把所有不同键放进 Python 内存，也不生成连接结果。支持组合键、不同的左右键名、
四种等值连接行数、唯一性和匹配覆盖策略。JSON 只包含统计，不输出数据值。

需要 Python 3.11+，无第三方运行依赖；从仓库安装：

```console
python -m venv .venv
```

Windows 激活 `.venv\Scripts\activate`，macOS/Linux 使用 `source .venv/bin/activate`。

```console
python -m pip install .
python -m join_grain examples/orders.csv examples/customers.csv --left-key customer_id --left-key region
```

示例为合成数据，故意返回 1，表示 many-to-one 策略失败。预估 inner=4、left=6、
right=5、full=7。0=策略通过，1=策略失败，2=输入或 I/O 错误，130=中断。

空键分量视为 NULL，互不匹配；不进行数字转换、去空格、大小写折叠。
重复表头、缺列、行宽错误、错误编码或引号会停止检查。原文件不改动。
`--temp-dir` 可指定已存在的私有临时目录。临时数据库包含原始键，统计也可能敏感；
不是加密或安全擦除工具。崩溃可能留下临时目录，确认进程停止后再清理。

默认每个输入最多一千万条记录、每个字段一百万字符。缓存设置不是总内存硬限制。
只检查所提供的稳定导出文件，不保证后续 SQL 的类型转换、排序规则或快照相同。
不计算金额，不执行连接。详细语义和限制见英文 README。

运行测试：`python -m unittest discover -s tests -v`。卸载：
`python -m pip uninstall join-grain`，再清理不需要的虚拟环境、构建产物和输出。
版本 0.1.0，MIT 许可证。
