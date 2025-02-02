# 天天吃饱饭

这是一个基于 Flask 的币安期货期货交易精细化系统结合了多周期共振，集成了 Binance API，提供了AI分析、交易对分析、数据分析、盈利管理、仓位管理等功能，提供1-10倍的合约管理。

## 功能特性

- 用户认证
- 山寨季分析
- 期货交易对AI分析
- 做空还多AI分析
- K线数据获取
- 订单管理（创建、查看、修改）
- 挂单管理
- 止盈止损设置
- 仓位管理
- EMA22 多周期共振



### AI 分析
![AI 分析](img/ai.png)
![AI 分析1](img/ai分析1.png)
![AI 分析2](img/ai分析2.png)

### 下单管理
![下单管理](img/下单管理.png)

### 交易对分析
![交易对分析](img/交易对分析.png)

### 山寨季
![山寨季](img/山寨季.png)

### 仙人指路
![仙人指路](img/仙人指路.png)

## 主要依赖库 必读

- Flask: Web 应用框架
- Flask-SQLAlchemy: 数据库 ORM,创建好qihuo库
- PyMySQL: MySQL 数据库连接器 记住修改app.py app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:10086@127.0.0.1:3306/qihuo'
- Binance API: 用于与 Binance 交易所交互
- 相关ai功能需要注册，https://build.nvidia.com/explore/discover#llama3-70b 免费替换的，直接替换 get_statistics_with_ai.py NVIDIA_API_KEY

详细的依赖列表请参考 `requirements.txt` 文件。

## 安装依赖

在开始之前，请确保您已安装 Python 3.7+。然后，按照以下步骤安装所需依赖：

1. 克隆项目到本地：

   ```
   git clone [您的项目 URL]
   cd [项目目录]
   ```

2. 安装所需的 Python 包：

   ```
   pip install -r requirements.txt
   ```

## 项目结构

```
./
├── app.py                    # 主应用文件
├── app.pybak                 # 主应用文件备份
├── auth.py                   # 认证模块
├── binance_module.py         # Binance API 相关模块
├── extensions.py             # Flask 扩展实例（如 db）
├── get_futures_symbols.py    # 获取期货交易对信息
├── get_klines.py             # 获取 K 线数据
├── get_statistics_all.py     # 获取所有交易统计信息
├── get_statistics.py         # 获取交易统计信息
├── models.py                 # 数据库模型
├── order_check.py            # 订单检查功能
├── order_management.py       # 订单管理功能
├── pending_order.py          # 挂单管理
├── position_management.py    # 仓位管理功能
├── README.md                 # 项目说明文档
├── requirements.txt          # 项目依赖列表
├── take_profit_stop_loss.py  # 止盈止损设置
└── templates/                # HTML 模板目录
```

## 模块说明

1. app.py: 主应用文件，包含 Flask 应用的配置和初始化。
2. auth.py: 用户认证模块，处理登录、注册等功能。
3. binance_module.py: 与 Binance API 交互的模块。
4. get_futures_symbols.py: 获取期货交易对信息。
5. get_klines.py: 获取 K 线数据。
6. get_statistics.py 和 get_statistics_all.py: 获取交易统计信息。
7. order_management.py: 订单管理功能。
8. order_check.py: 订单检查功能。
9. pending_order.py: 挂单管理。
10. take_profit_stop_loss.py: 止盈止损设置。
11. position_management.py: 仓位管理功能。

## 配置

1. 数据库配置：
   在 `app.py` 中，修改 `SQLALCHEMY_DATABASE_URI` 以匹配您的数据库设置。

2. 密钥配置：
   修改 `SECRET_KEY` 为一个安全的随机字符串。

3. Binance API 配置：
   在 `binance_module.py` 中设置您的 Binance API 密钥和密钥。

## 运行应用

使用提供的 run.sh 脚本运行应用：

```
./run.sh
```

或者直接运行 Python 文件：

```
python app.py
```

## 数据分析设置

使用 `setup_数据分析.sh` 脚本来设置数据分析环境：

```
./setup_数据分析.sh
```

## 开发指南

### 导入新模板

1. 在 `templates` 目录下创建新的 HTML 文件。

2. 在相应的路由函数中使用 `render_template` 渲染模板：

   ```python
   from flask import render_template

   @app.route('/new_page')
   def new_page():
       return render_template('new_page.html')
   ```

3. 如果需要在模板中使用变量，可以在 `render_template` 函数中传递：

   ```python
   @app.route('/greeting/<name>')
   def greeting(name):
       return render_template('greeting.html', name=name)
   ```

   在 `greeting.html` 中：
   ```html
   <h1>Hello, {{ name }}!</h1>
   ```

### 开发新模块

1. 创建新的 Python 文件，例如 `new_module.py`。

2. 在新模块中定义必要的函数和类：

   ```python
   # new_module.py
   
   def new_function():
       # 函数实现
       pass

   class NewClass:
       # 类实现
       pass
   ```

3. 在主应用文件（`app.py`）或其他相关模块中导入新模块：

   ```python
   from new_module import new_function, NewClass
   ```

4. 如果新模块包含路由，可以使用 Flask 的蓝图功能：

   在 `new_module.py` 中：
   ```python
   from flask import Blueprint

   new_module_bp = Blueprint('new_module', __name__)

   @new_module_bp.route('/new_route')
   def new_route():
       return "This is a new route"
   ```

   在 `app.py` 中注册蓝图：
   ```python
   from new_module import new_module_bp
   app.register_blueprint(new_module_bp)
   ```

5. 如果新模块需要访问数据库或其他 Flask 扩展，可以从 `extensions.py` 中导入：

   ```python
   from extensions import db
   ```

6. 更新 `requirements.txt`：如果新模块需要额外的依赖，确保将它们添加到 `requirements.txt` 文件中。

7. 文档化：在本 README 文件中添加新模块的说明，并在代码中添加适当的注释和文档字符串。

遵循这些步骤可以帮助您保持项目的组织性和可维护性。记得在开发新功能时遵循 Python 的编码规范（如 PEP 8）和项目的既定模式。

## 注意事项

- 确保所有的 .py 文件都有正确的执行权限。
- 在生产环境中部署时，请确保关闭调试模式（`debug=False`）。
- 定期更新依赖包以获取最新的安全补丁。
- 确保妥善保管所有敏感信息，如数据库凭证和 API 密钥。
- 考虑使用环境变量来存储敏感配置，而不是直接在代码中硬编码。

## 贡献

欢迎提交 pull requests。对于重大更改，请先开 issue 讨论您想要改变的内容。在开发新功能或修复 bug 时，请遵循上述开发指南。

## 许可证

[MIT](https://choosealicense.com/licenses/mit/)
## 定制联系
![定制联系](img/联系.jpg)

