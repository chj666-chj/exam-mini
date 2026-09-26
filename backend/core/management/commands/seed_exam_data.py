"""导入软考（软件设计师 / 信息系统项目管理师）完整测试数据。

用法：
    python manage.py seed_exam_data          # 仅导入软考数据（清空旧软考数据后重新导入）
    python manage.py seed_exam_data --reset  # 清空所有集合后导入（含原有演示数据会被清除）
    python manage.py seed_exam_data --append # 追加模式，不清空

数据结构：
    exam      → 科目维度（软件设计师、信息系统项目管理师）
    subjects  → 章节维度（按官方大纲划分，pid 指向 exam._id）
    questions → 习题数据（examid 指向 subjects._id，含题型/难度/解析/配图）
"""
import json

from django.core.management.base import BaseCommand

from core.models import Document

# ---------------------------------------------------------------------------
# 科目维度数据
# ---------------------------------------------------------------------------
EXAMS = [
    {
        "_id": "RK_RJJS",
        "name": "软件设计师",
        "description": "全国计算机技术与软件专业技术资格（水平）考试 - 软件设计师（中级）",
        "duration": 150,
        "questionTypes": [
            {"type": "single", "label": "单选题", "count": 60, "score": 1},
            {"type": "multiple", "label": "多选题", "count": 10, "score": 2},
            {"type": "judge", "label": "判断题", "count": 10, "score": 1},
        ],
        "totalScore": 90,
        "passScore": 54,
        "category": "软考中级",
    },
    {
        "_id": "RK_XXXT",
        "name": "信息系统项目管理师",
        "description": "全国计算机技术与软件专业技术资格（水平）考试 - 信息系统项目管理师（高级）",
        "duration": 180,
        "questionTypes": [
            {"type": "single", "label": "单选题", "count": 50, "score": 1},
            {"type": "multiple", "label": "多选题", "count": 15, "score": 2},
            {"type": "judge", "label": "判断题", "count": 10, "score": 1},
        ],
        "totalScore": 90,
        "passScore": 54,
        "category": "软考高级",
    },
]

# ---------------------------------------------------------------------------
# 章节维度数据
# ---------------------------------------------------------------------------
SUBJECTS = [
    # ===== 软件设计师 =====
    {
        "_id": "RK_RJJS_CH01",
        "name": "计算机系统基础知识",
        "pid": "RK_RJJS",
        "description": "计算机系统的组成、数据表示、校验码、CPU结构、存储系统、总线与中断等基础知识",
        "knowledgePoints": ["数制转换与编码", "校验码（奇偶/CRC）", "CPU组成与指令周期", "存储系统层次结构", "总线结构", "中断机制"],
        "sortWeight": 1,
    },
    {
        "_id": "RK_RJJS_CH02",
        "name": "程序语言基础知识",
        "pid": "RK_RJJS",
        "description": "汇编/编译/解释原理、语法分析、表达式、参数传递、函数调用等",
        "knowledgePoints": ["编译与解释", "词法/语法分析", "后缀表达式", "参数传递方式", "递归与栈"],
        "sortWeight": 2,
    },
    {
        "_id": "RK_RJJS_CH03",
        "name": "操作系统基础知识",
        "pid": "RK_RJJS",
        "description": "进程管理、存储管理、文件管理、设备管理、PV操作与死锁",
        "knowledgePoints": ["进程状态转换", "PV操作与信号量", "银行家算法", "页面置换算法", "磁盘调度", "死锁条件"],
        "sortWeight": 3,
    },
    {
        "_id": "RK_RJJS_CH04",
        "name": "软件工程基础知识",
        "pid": "RK_RJJS",
        "description": "软件生命周期、开发模型、需求分析、测试方法、UML、项目管理基础",
        "knowledgePoints": ["瀑布/敏捷/螺旋模型", "黑盒与白盒测试", "UML图", "需求获取与分析", "软件配置管理"],
        "sortWeight": 4,
    },
    {
        "_id": "RK_RJJS_CH05",
        "name": "数据结构与算法",
        "pid": "RK_RJJS",
        "description": "线性表、栈/队列、树/图、排序与查找算法、时间复杂度分析",
        "knowledgePoints": ["线性表存储", "二叉树遍历", "图的DFS/BFS", "排序算法比较", "散列查找", "时间复杂度"],
        "sortWeight": 5,
    },
    {
        "_id": "RK_RJJS_CH06",
        "name": "数据库系统",
        "pid": "RK_RJJS",
        "description": "关系模型、SQL、范式、ER图、事务与并发控制",
        "knowledgePoints": ["关系代数", "SQL语句", "范式与函数依赖", "ER模型转换", "事务ACID", "并发控制与锁"],
        "sortWeight": 6,
    },
    # ===== 信息系统项目管理师 =====
    {
        "_id": "RK_XXXT_CH01",
        "name": "信息系统基础",
        "pid": "RK_XXXT",
        "description": "信息系统概念、生命周期、开发方法、企业信息化战略",
        "knowledgePoints": ["信息系统定义", "信息系统生命周期", "结构化/面向对象开发方法", "企业架构", "信息化战略"],
        "sortWeight": 1,
    },
    {
        "_id": "RK_XXXT_CH02",
        "name": "项目管理一般知识",
        "pid": "RK_XXXT",
        "description": "项目与项目管理概念、项目组织结构、项目生命周期、PMBOK知识领域",
        "knowledgePoints": ["项目定义与特征", "项目组织结构（职能/矩阵/项目型）", "PMBOK十大知识领域", "项目生命周期", "过程组"],
        "sortWeight": 2,
    },
    {
        "_id": "RK_XXXT_CH03",
        "name": "项目立项管理",
        "pid": "RK_XXXT",
        "description": "项目立项流程、可行性研究、项目论证与评估",
        "knowledgePoints": ["立项流程", "可行性研究内容", "成本效益分析", "项目论证", "项目评估"],
        "sortWeight": 3,
    },
    {
        "_id": "RK_XXXT_CH04",
        "name": "项目整体管理",
        "pid": "RK_XXXT",
        "description": "项目章程、项目管理计划、变更控制、整体变更控制流程",
        "knowledgePoints": ["项目章程", "项目管理计划", "指导与管理项目执行", "整体变更控制", "项目收尾"],
        "sortWeight": 4,
    },
    {
        "_id": "RK_XXXT_CH05",
        "name": "项目范围管理",
        "pid": "RK_XXXT",
        "description": "需求收集、范围定义、WBS、范围确认与范围控制",
        "knowledgePoints": ["范围定义", "WBS创建", "范围确认", "范围控制", "需求跟踪矩阵"],
        "sortWeight": 5,
    },
    {
        "_id": "RK_XXXT_CH06",
        "name": "项目进度管理",
        "pid": "RK_XXXT",
        "description": "活动定义与排序、工期估算、关键路径法、进度控制",
        "knowledgePoints": ["活动排序", "关键路径法CPM", "甘特图", "进度压缩（赶工/快速跟进）", "三点估算"],
        "sortWeight": 6,
    },
]


# ---------------------------------------------------------------------------
# 习题数据
# ---------------------------------------------------------------------------
def make_q(_id, title, qtype, difficulty, examid, options, answer, explanation,
           typename=None, image=None, image_desc=None, image_type=None):
    """生成一条 question 文档。"""
    type_map = {"single": "单选题", "multiple": "多选题", "judge": "判断题"}
    doc = {
        "_id": _id,
        "title": title,
        "qtype": qtype,
        "type": qtype,
        "typename": typename or type_map.get(qtype, qtype),
        "typecode": qtype,
        "difficulty": difficulty,
        "examid": examid,
        "chapter": examid,
        "answer": answer,
        "explanation": explanation,
        "comments": explanation,
        "options": options,
    }
    if image:
        doc["image"] = image
        doc["imageDesc"] = image_desc or ""
        doc["imageType"] = image_type or "chart"
    return doc


QUESTIONS = [
    # ===== 软件设计师 CH01 - 计算机系统基础知识 =====
    make_q(
        "RK_RJJS_CH01_Q01",
        "在计算机中，以下哪种编码方式既能够表示正数和负数，又使得零的表示是唯一的？",
        "single", 2, "RK_RJJS_CH01",
        [
            {"code": "A", "content": "原码", "value": 0},
            {"code": "B", "content": "反码", "value": 0},
            {"code": "C", "content": "补码", "value": 1},
            {"code": "D", "content": "移码", "value": 0},
        ],
        "C",
        "补码的零表示唯一（全0），而原码和反码的零有+0和-0两种表示。移码主要用于浮点数阶码表示。"
    ),
    make_q(
        "RK_RJJS_CH01_Q02",
        "某机器字长16位，采用补码表示有符号整数时，其表示范围是？",
        "single", 2, "RK_RJJS_CH01",
        [
            {"code": "A", "content": "-32768 ~ +32767", "value": 1},
            {"code": "B", "content": "-32767 ~ +32767", "value": 0},
            {"code": "C", "content": "0 ~ 65535", "value": 0},
            {"code": "D", "content": "-32768 ~ +32768", "value": 0},
        ],
        "A",
        "n位补码的表示范围是 -2^(n-1) ~ 2^(n-1)-1，16位时为 -2^15 ~ 2^15-1 = -32768 ~ +32767。"
    ),
    make_q(
        "RK_RJJS_CH01_Q03",
        "以下关于CRC循环冗余校验码的叙述中，正确的有？",
        "multiple", 3, "RK_RJJS_CH01",
        [
            {"code": "A", "content": "CRC能够检测出所有奇数个错误", "value": 1},
            {"code": "B", "content": "CRC能够检测出所有双位错误", "value": 1},
            {"code": "C", "content": "CRC能够纠正错误", "value": 0},
            {"code": "D", "content": "CRC校验码的生成与多项式有关", "value": 1},
        ],
        "ABD",
        "CRC是一种检错码，不能纠错（C错误）。CRC能检测所有奇数个错误、双位错误以及突发长度小于等于生成多项式长度的突发错误。CRC校验基于多项式除法运算。"
    ),
    make_q(
        "RK_RJJS_CH01_Q04",
        "Cache存储器是为了解决CPU与主存之间速度不匹配的问题而设置的。",
        "judge", 1, "RK_RJJS_CH01",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "Cache（高速缓存）利用程序的局部性原理，在CPU和主存之间增加一层高速存储器，缓解速度差距。"
    ),
    make_q(
        "RK_RJJS_CH01_Q05",
        "在计算机总线结构中，以下关于总线分类的描述，正确的是？",
        "single", 2, "RK_RJJS_CH01",
        [
            {"code": "A", "content": "数据总线、地址总线和控制总线", "value": 1},
            {"code": "B", "content": "输入总线、输出总线和控制总线", "value": 0},
            {"code": "C", "content": "串行总线、并行总线和混合总线", "value": 0},
            {"code": "D", "content": "内总线、外总线和系统总线", "value": 0},
        ],
        "A",
        "按功能划分，系统总线分为数据总线（传输数据）、地址总线（传输地址）和控制总线（传输控制信号）。"
    ),

    # ===== 软件设计师 CH02 - 程序语言基础知识 =====
    make_q(
        "RK_RJJS_CH02_Q01",
        "编译器和解释器是两种不同的语言翻译程序。以下关于它们的叙述中，正确的是？",
        "single", 2, "RK_RJJS_CH02",
        [
            {"code": "A", "content": "编译器会生成目标代码，解释器不生成目标代码", "value": 1},
            {"code": "B", "content": "编译器和解释器都会生成目标代码", "value": 0},
            {"code": "C", "content": "编译器不生成目标代码，解释器生成目标代码", "value": 0},
            {"code": "D", "content": "编译器和解释器都不生成目标代码", "value": 0},
        ],
        "A",
        "编译器将源程序翻译成目标程序（可执行代码），解释器逐句翻译并执行源程序，不产生目标代码。"
    ),
    make_q(
        "RK_RJJS_CH02_Q02",
        "表达式 a+b*(c-d) 的后缀表达式（逆波兰式）是？",
        "single", 3, "RK_RJJS_CH02",
        [
            {"code": "A", "content": "a b c d - * +", "value": 1},
            {"code": "B", "content": "a b + c d - *", "value": 0},
            {"code": "C", "content": "a b c d * - +", "value": 0},
            {"code": "D", "content": "+ a * b - c d", "value": 0},
        ],
        "A",
        "中缀转后缀：a+b*(c-d) → a b c d - * +。先算c-d（后缀: c d -），再算b*(c-d)（后缀: b c d - *），最后算a+（后缀: a b c d - * +）。",
        image="rk_rjjs_ch02_q02_expr_tree",
        image_desc="表达式 a+b*(c-d) 对应的语法树，根节点为+，左子树为a，右子树为*（左b右-（左c右d））",
        image_type="structure"
    ),
    make_q(
        "RK_RJJS_CH02_Q03",
        "以下关于函数调用时参数传递方式的叙述，正确的有？",
        "multiple", 2, "RK_RJJS_CH02",
        [
            {"code": "A", "content": "值传递不会改变实参的值", "value": 1},
            {"code": "B", "content": "引用传递可以改变实参的值", "value": 1},
            {"code": "C", "content": "值传递和引用传递的效果完全相同", "value": 0},
            {"code": "D", "content": "C语言只支持值传递，可通过传指针模拟引用传递", "value": 1},
        ],
        "ABD",
        "值传递将实参的副本传给形参，不影响实参（A正确）；引用传递直接操作实参（B正确）；两者效果不同（C错误）；C语言本身只有值传递，传指针是值传递的一种应用（D正确）。"
    ),
    make_q(
        "RK_RJJS_CH02_Q04",
        "在递归函数调用过程中，系统使用的数据结构是栈。",
        "judge", 1, "RK_RJJS_CH02",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "递归调用时，每次调用的参数、局部变量和返回地址都压入栈中，符合后进先出（LIFO）的特性。"
    ),
    make_q(
        "RK_RJJS_CH02_Q05",
        "在语法分析中，自上而下分析方法不包括以下哪个？",
        "single", 2, "RK_RJJS_CH02",
        [
            {"code": "A", "content": "递归下降分析法", "value": 0},
            {"code": "B", "content": "LL(1)分析法", "value": 0},
            {"code": "C", "content": "算符优先分析法", "value": 1},
            {"code": "D", "content": "预测分析法", "value": 0},
        ],
        "C",
        "自上而下分析包括递归下降分析、LL(1)分析和预测分析。算符优先分析属于自下而上分析方法。"
    ),

    # ===== 软件设计师 CH03 - 操作系统基础知识 =====
    make_q(
        "RK_RJJS_CH03_Q01",
        "若系统中有n个进程共享m个同类资源，每个进程最多申请k个资源，则系统不会发生死锁的条件是？",
        "single", 3, "RK_RJJS_CH03",
        [
            {"code": "A", "content": "n*(k-1)+1 <= m", "value": 1},
            {"code": "B", "content": "n*k <= m", "value": 0},
            {"code": "C", "content": "n*(k-1) < m", "value": 0},
            {"code": "D", "content": "n*(k+1) <= m", "value": 0},
        ],
        "A",
        "最坏情况下每个进程都已获得k-1个资源，此时共占用n*(k-1)个。只要剩余至少1个资源（即 n*(k-1)+1 <= m），就有一个进程能获得全部资源并释放，不会死锁。"
    ),
    make_q(
        "RK_RJJS_CH03_Q02",
        "以下关于进程状态转换的叙述中，不可能发生的是？",
        "single", 2, "RK_RJJS_CH03",
        [
            {"code": "A", "content": "就绪 → 运行", "value": 0},
            {"code": "B", "content": "运行 → 阻塞", "value": 0},
            {"code": "C", "content": "阻塞 → 运行", "value": 1},
            {"code": "D", "content": "运行 → 就绪", "value": 0},
        ],
        "C",
        "进程状态转换中，阻塞状态不能直接转为运行状态，必须先转为就绪状态，再由调度程序从就绪队列中调度为运行。",
        image="rk_rjjs_ch03_q02_state_diagram",
        image_desc="进程三态模型状态转换图：就绪↔运行（调度/时间片完），运行→阻塞（等待事件），阻塞→就绪（事件完成）",
        image_type="flowchart"
    ),
    make_q(
        "RK_RJJS_CH03_Q03",
        "在页面置换算法中，以下哪些算法可能产生Belady异常（分配页面数增加，缺页率反而上升）？",
        "multiple", 3, "RK_RJJS_CH03",
        [
            {"code": "A", "content": "FIFO（先进先出）", "value": 1},
            {"code": "B", "content": "LRU（最近最久未使用）", "value": 0},
            {"code": "C", "content": "OPT（最佳置换）", "value": 0},
            {"code": "D", "content": "Clock（时钟置换）", "value": 0},
        ],
        "A",
        "Belady异常只在FIFO算法中出现。LRU和OPT等栈式算法不会出现此异常，因为它们满足栈式算法的包含性。"
    ),
    make_q(
        "RK_RJJS_CH03_Q04",
        "银行家算法是一种死锁避免算法，它在分配资源前先检查分配后系统是否处于安全状态。",
        "judge", 1, "RK_RJJS_CH03",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "银行家算法通过安全性检查来判断资源分配后是否存在安全序列，如果存在则允许分配，否则拒绝，从而避免死锁。"
    ),
    make_q(
        "RK_RJJS_CH03_Q05",
        "PV操作中，P操作（wait）和V操作（signal）分别对信号量执行什么操作？",
        "single", 1, "RK_RJJS_CH03",
        [
            {"code": "A", "content": "P: 减1，V: 加1", "value": 1},
            {"code": "B", "content": "P: 加1，V: 减1", "value": 0},
            {"code": "C", "content": "P: 减1，V: 减1", "value": 0},
            {"code": "D", "content": "P: 加1，V: 加1", "value": 0},
        ],
        "A",
        "P操作（wait/proberen）将信号量减1，若结果<0则进程阻塞；V操作（signal/verhogen）将信号量加1，若结果<=0则唤醒一个等待进程。"
    ),

    # ===== 软件设计师 CH04 - 软件工程基础知识 =====
    make_q(
        "RK_RJJS_CH04_Q01",
        "在软件测试中，以下哪种测试方法主要关注程序内部逻辑结构？",
        "single", 1, "RK_RJJS_CH04",
        [
            {"code": "A", "content": "黑盒测试", "value": 0},
            {"code": "B", "content": "白盒测试", "value": 1},
            {"code": "C", "content": "等价类划分", "value": 0},
            {"code": "D", "content": "边界值分析", "value": 0},
        ],
        "B",
        "白盒测试关注程序内部逻辑结构，测试者需要了解代码的内部实现，常用方法有语句覆盖、判定覆盖、条件覆盖等。黑盒测试关注功能而非内部结构。"
    ),
    make_q(
        "RK_RJJS_CH04_Q02",
        "以下关于软件开发模型的叙述中，正确的有？",
        "multiple", 2, "RK_RJJS_CH04",
        [
            {"code": "A", "content": "瀑布模型要求每个阶段完成后才进入下一阶段", "value": 1},
            {"code": "B", "content": "螺旋模型结合了瀑布模型和演化模型的优点，并增加了风险分析", "value": 1},
            {"code": "C", "content": "敏捷开发强调文档优先于代码", "value": 0},
            {"code": "D", "content": "增量模型允许分批交付软件功能", "value": 1},
        ],
        "ABD",
        "瀑布模型严格按阶段顺序（A正确）；螺旋模型加入了风险分析（B正确）；敏捷开发强调可工作软件优于详尽的文档，而非文档优先（C错误）；增量模型分批构建和交付（D正确）。",
        image="rk_rjjs_ch04_q02_dev_models",
        image_desc="瀑布模型、螺旋模型、增量模型的对比流程图",
        image_type="flowchart"
    ),
    make_q(
        "RK_RJJS_CH04_Q03",
        "UML中的类图属于哪种类型的图？",
        "single", 1, "RK_RJJS_CH04",
        [
            {"code": "A", "content": "行为图", "value": 0},
            {"code": "B", "content": "结构图", "value": 1},
            {"code": "C", "content": "用例图", "value": 0},
            {"code": "D", "content": "交互图", "value": 0},
        ],
        "B",
        "UML图分为结构图和行为图两大类。类图属于结构图，用于描述系统的静态结构。行为图包括活动图、状态图、用例图等。"
    ),
    make_q(
        "RK_RJJS_CH04_Q04",
        "软件配置管理（SCM）的目的是控制软件变更，确保软件产品的完整性和可追溯性。",
        "judge", 1, "RK_RJJS_CH04",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "软件配置管理（SCM）通过标识、控制、状态记录和审计四项活动，管理软件生命周期中的变更，确保产品完整性。"
    ),
    make_q(
        "RK_RJJS_CH04_Q05",
        "在软件能力成熟度模型（CMM）中，最高级别是？",
        "single", 2, "RK_RJJS_CH04",
        [
            {"code": "A", "content": "已定义级", "value": 0},
            {"code": "B", "content": "优化级", "value": 1},
            {"code": "C", "content": "量化管理级", "value": 0},
            {"code": "D", "content": "持续改进级", "value": 0},
        ],
        "B",
        "CMM五个级别：1初始级→2可重复级→3已定义级→4量化管理级→5优化级。最高级别是5级优化级，强调持续过程改进。"
    ),

    # ===== 软件设计师 CH05 - 数据结构与算法 =====
    make_q(
        "RK_RJJS_CH05_Q01",
        "对一棵有n个节点的二叉树进行中序遍历，其时间复杂度为？",
        "single", 1, "RK_RJJS_CH05",
        [
            {"code": "A", "content": "O(1)", "value": 0},
            {"code": "B", "content": "O(log n)", "value": 0},
            {"code": "C", "content": "O(n)", "value": 1},
            {"code": "D", "content": "O(n^2)", "value": 0},
        ],
        "C",
        "中序遍历需要访问每个节点恰好一次，共n个节点，因此时间复杂度为O(n)。"
    ),
    make_q(
        "RK_RJJS_CH05_Q02",
        "以下排序算法中，哪些算法在最坏情况下的时间复杂度为O(n^2)？",
        "multiple", 2, "RK_RJJS_CH05",
        [
            {"code": "A", "content": "快速排序", "value": 1},
            {"code": "B", "content": "归并排序", "value": 0},
            {"code": "C", "content": "冒泡排序", "value": 1},
            {"code": "D", "content": "堆排序", "value": 0},
        ],
        "AC",
        "快速排序最坏情况（数组已有序）退化为O(n^2)；冒泡排序始终为O(n^2)；归并排序和堆排序的最坏时间复杂度均为O(n log n)。",
        image="rk_rjjs_ch05_q02_sort_compare",
        image_desc="各排序算法的时间复杂度对比表格",
        image_type="chart"
    ),
    make_q(
        "RK_RJJS_CH05_Q03",
        "在图的遍历中，广度优先搜索（BFS）使用的数据结构是？",
        "single", 1, "RK_RJJS_CH05",
        [
            {"code": "A", "content": "栈", "value": 0},
            {"code": "B", "content": "队列", "value": 1},
            {"code": "C", "content": "堆", "value": 0},
            {"code": "D", "content": "散列表", "value": 0},
        ],
        "B",
        "BFS使用队列实现，按层次顺序访问节点。DFS使用栈实现（或递归调用栈），按深度方向访问。"
    ),
    make_q(
        "RK_RJJS_CH05_Q04",
        "散列表中使用链地址法解决冲突时，装填因子（负载因子）可以大于1。",
        "judge", 2, "RK_RJJS_CH05",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "链地址法中每个桶存一个链表，装填因子=元素数/桶数，可以大于1（多个元素映射到同一桶）。开放地址法要求装填因子<1。"
    ),
    make_q(
        "RK_RJJS_CH05_Q05",
        "对含有n个关键字的散列表进行查找，在等概率情况下，采用线性探测法解决冲突的平均查找长度取决于？",
        "single", 3, "RK_RJJS_CH05",
        [
            {"code": "A", "content": "散列表长度", "value": 0},
            {"code": "B", "content": "装填因子", "value": 1},
            {"code": "C", "content": "关键字个数n", "value": 0},
            {"code": "D", "content": "散列函数类型", "value": 0},
        ],
        "B",
        "散列表查找的平均查找长度主要取决于装填因子（α=元素数/表长），而不是散列表长度或关键字个数本身。线性探测法的成功查找ASL≈(1+1/(1-α))/2。"
    ),

    # ===== 软件设计师 CH06 - 数据库系统 =====
    make_q(
        "RK_RJJS_CH06_Q01",
        "在关系数据库中，以下哪种范式要求消除非主属性对候选键的部分函数依赖？",
        "single", 2, "RK_RJJS_CH06",
        [
            {"code": "A", "content": "第一范式（1NF）", "value": 0},
            {"code": "B", "content": "第二范式（2NF）", "value": 1},
            {"code": "C", "content": "第三范式（3NF）", "value": 0},
            {"code": "D", "content": "BCNF", "value": 0},
        ],
        "B",
        "2NF在1NF基础上消除非主属性对候选键的部分函数依赖；3NF消除传递依赖；BCNF消除主属性对候选键的部分和传递依赖。",
        image="rk_rjjs_ch06_q01_normal_forms",
        image_desc="数据库范式层次图：1NF→2NF→3NF→BCNF→4NF→5NF，每层解决的问题标注",
        image_type="structure"
    ),
    make_q(
        "RK_RJJS_CH06_Q02",
        "SQL语句中，以下哪些子句可以用于对查询结果进行聚合计算？",
        "multiple", 2, "RK_RJJS_CH06",
        [
            {"code": "A", "content": "GROUP BY", "value": 1},
            {"code": "B", "content": "HAVING", "value": 1},
            {"code": "C", "content": "ORDER BY", "value": 0},
            {"code": "D", "content": "DISTINCT", "value": 0},
        ],
        "AB",
        "GROUP BY用于分组聚合，HAVING用于对分组结果过滤。ORDER BY用于排序，DISTINCT用于去重，都不是聚合计算。"
    ),
    make_q(
        "RK_RJJS_CH06_Q03",
        "事务的ACID特性中，'I'代表的是？",
        "single", 1, "RK_RJJS_CH06",
        [
            {"code": "A", "content": "完整性（Integrity）", "value": 0},
            {"code": "B", "content": "隔离性（Isolation）", "value": 1},
            {"code": "C", "content": "即时性（Immediacy）", "value": 0},
            {"code": "D", "content": "不可逆性（Irreversibility）", "value": 0},
        ],
        "B",
        "ACID：A=原子性（Atomicity）、C=一致性（Consistency）、I=隔离性（Isolation）、D=持久性（Durability）。隔离性指并发事务间互不干扰。"
    ),
    make_q(
        "RK_RJJS_CH06_Q04",
        "在ER模型转换为关系模式时，一个M:N联系必须转换为一个独立的关系模式。",
        "judge", 2, "RK_RJJS_CH06",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "1:1联系可并入任一端实体；1:N联系可并入N端实体；M:N联系必须建立独立关系模式，包含两端实体的主键作为外键。"
    ),
    make_q(
        "RK_RJJS_CH06_Q05",
        "设有关系R(A,B,C,D)，函数依赖集F={A→B, B→C, C→D}，则R的候选键是？",
        "single", 3, "RK_RJJS_CH06",
        [
            {"code": "A", "content": "A", "value": 1},
            {"code": "B", "content": "B", "value": 0},
            {"code": "C", "content": "AB", "value": 0},
            {"code": "D", "content": "ABC", "value": 0},
        ],
        "A",
        "A→B→C→D传递依赖，A的闭包A+={A,B,C,D}包含所有属性，因此A是候选键。B+={B,C,D}不含A，AB和ABC都不是最小候选键。"
    ),

    # ===== 信息系统项目管理师 CH01 - 信息系统基础 =====
    make_q(
        "RK_XXXT_CH01_Q01",
        "信息系统的生命周期通常分为哪几个阶段？",
        "single", 1, "RK_XXXT_CH01",
        [
            {"code": "A", "content": "立项、开发、运维、消亡", "value": 1},
            {"code": "B", "content": "规划、分析、设计、实现", "value": 0},
            {"code": "C", "content": "需求、设计、编码、测试", "value": 0},
            {"code": "D", "content": "启动、执行、监控、收尾", "value": 0},
        ],
        "A",
        "信息系统生命周期分为：立项阶段→开发阶段→运维阶段→消亡阶段。B是软件生命周期，D是项目管理过程组。",
        image="rk_xxxt_ch01_q01_lifecycle",
        image_desc="信息系统生命周期四阶段流程图：立项→开发→运维→消亡",
        image_type="flowchart"
    ),
    make_q(
        "RK_XXXT_CH01_Q02",
        "以下关于企业信息化的叙述中，正确的有？",
        "multiple", 2, "RK_XXXT_CH01",
        [
            {"code": "A", "content": "企业信息化是企业利用信息技术优化业务流程的过程", "value": 1},
            {"code": "B", "content": "ERP系统是企业信息化的重要组成", "value": 1},
            {"code": "C", "content": "企业信息化只需要技术部门参与", "value": 0},
            {"code": "D", "content": "企业信息化是一项长期系统性工程", "value": 1},
        ],
        "ABD",
        "企业信息化是利用信息技术优化各环节的综合工程（A正确），ERP是核心系统之一（B正确），需要全员参与而非仅技术部门（C错误），是长期系统性工程（D正确）。"
    ),
    make_q(
        "RK_XXXT_CH01_Q03",
        "面向对象开发方法的核心特征不包括以下哪项？",
        "single", 2, "RK_XXXT_CH01",
        [
            {"code": "A", "content": "封装", "value": 0},
            {"code": "B", "content": "继承", "value": 0},
            {"code": "C", "content": "模块化", "value": 1},
            {"code": "D", "content": "多态", "value": 0},
        ],
        "C",
        "面向对象的核心特征是封装、继承、多态。模块化是结构化开发方法的特征，不是面向对象的核心特征。"
    ),
    make_q(
        "RK_XXXT_CH01_Q04",
        "结构化开发方法强调自顶向下、逐步求精的设计思想。",
        "judge", 1, "RK_XXXT_CH01",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "结构化开发方法以数据流图为工具，采用自顶向下、逐步求精的策略，将复杂问题分解为可管理的模块。"
    ),
    make_q(
        "RK_XXXT_CH01_Q05",
        "在企业架构（EA）中，以下哪个框架是最常用的企业架构框架？",
        "single", 2, "RK_XXXT_CH01",
        [
            {"code": "A", "content": "ITIL", "value": 0},
            {"code": "B", "content": "TOGAF", "value": 1},
            {"code": "C", "content": "COBIT", "value": 0},
            {"code": "D", "content": "ISO 27001", "value": 0},
        ],
        "B",
        "TOGAF（The Open Group Architecture Framework）是最广泛使用的企业架构框架，提供ADM（架构开发方法）方法论。ITIL是IT服务管理，COBIT是IT治理，ISO 27001是信息安全管理。"
    ),

    # ===== 信息系统项目管理师 CH02 - 项目管理一般知识 =====
    make_q(
        "RK_XXXT_CH02_Q01",
        "PMBOK中项目管理的十大知识领域不包括以下哪项？",
        "single", 2, "RK_XXXT_CH02",
        [
            {"code": "A", "content": "项目范围管理", "value": 0},
            {"code": "B", "content": "项目进度管理", "value": 0},
            {"code": "C", "content": "项目采购管理", "value": 0},
            {"code": "D", "content": "项目战略管理", "value": 1},
        ],
        "D",
        'PMBOK十大知识领域：整体、范围、进度、成本、质量、资源、沟通、风险、采购、相关方管理。不包含"项目战略管理"。',
        image="rk_xxxt_ch02_q01_pmbok",
        image_desc="PMBOK十大知识领域与五大过程组矩阵图",
        image_type="structure"
    ),
    make_q(
        "RK_XXXT_CH02_Q02",
        "以下关于项目组织结构的叙述中，正确的有？",
        "multiple", 2, "RK_XXXT_CH02",
        [
            {"code": "A", "content": "职能型组织中项目协调较为困难", "value": 1},
            {"code": "B", "content": "项目型组织中团队成员在项目结束后面临重新分配", "value": 1},
            {"code": "C", "content": "矩阵型组织兼有职能型和项目型的特点", "value": 1},
            {"code": "D", "content": "强矩阵型组织中项目经理的权力弱于职能经理", "value": 0},
        ],
        "ABC",
        "职能型组织各部门壁垒导致项目协调困难（A正确）；项目型组织项目结束后团队解散需重新分配（B正确）；矩阵型混合两者特点（C正确）；强矩阵中项目经理权力强于职能经理（D错误）。"
    ),
    make_q(
        "RK_XXXT_CH02_Q03",
        "项目管理的五个过程组按顺序是：启动→规划→执行→监控→收尾。",
        "judge", 1, "RK_XXXT_CH02",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "PMBOK五大过程组：启动过程组、规划过程组、执行过程组、监控过程组、收尾过程组。监控过程组贯穿项目始终，与其他过程组并行。"
    ),
    make_q(
        "RK_XXXT_CH02_Q04",
        "项目与日常运营的主要区别是？",
        "single", 1, "RK_XXXT_CH02",
        [
            {"code": "A", "content": "项目是临时的，日常运营是持续的", "value": 1},
            {"code": "B", "content": "项目不需要管理，日常运营需要管理", "value": 0},
            {"code": "C", "content": "项目不产生产品，日常运营产生产品", "value": 0},
            {"code": "D", "content": "项目没有目标，日常运营有目标", "value": 0},
        ],
        "A",
        "项目的核心特征是临时性（有明确的开始和结束）和独特性；日常运营是持续性和重复性的。两者都需要管理，都有目标，都可能产出产品或服务。"
    ),
    make_q(
        "RK_XXXT_CH02_Q05",
        "以下哪种项目组织结构中，项目成员需要向两个上级汇报？",
        "single", 2, "RK_XXXT_CH02",
        [
            {"code": "A", "content": "职能型", "value": 0},
            {"code": "B", "content": "项目型", "value": 0},
            {"code": "C", "content": "矩阵型", "value": 1},
            {"code": "D", "content": "复合型", "value": 0},
        ],
        "C",
        '矩阵型组织中，项目成员既属于职能部门又属于项目团队，需要同时向职能经理和项目经理汇报，存在"双重领导"特征。'
    ),

    # ===== 信息系统项目管理师 CH03 - 项目立项管理 =====
    make_q(
        "RK_XXXT_CH03_Q01",
        "项目可行性研究的内容通常包括以下哪些方面？",
        "multiple", 2, "RK_XXXT_CH03",
        [
            {"code": "A", "content": "技术可行性", "value": 1},
            {"code": "B", "content": "经济可行性", "value": 1},
            {"code": "C", "content": "法律可行性", "value": 1},
            {"code": "D", "content": "竞争对手可行性", "value": 0},
        ],
        "ABC",
        "可行性研究通常包括：技术可行性、经济可行性、法律可行性（运行可行性/社会可行性）。竞争对手分析属于市场分析，不属于标准可行性研究的四个维度之一。",
        image="rk_xxxt_ch03_q01_feasibility",
        image_desc="可行性研究四维度分析图：技术、经济、法律、运行",
        image_type="chart"
    ),
    make_q(
        "RK_XXXT_CH03_Q02",
        "在项目立项管理的成本效益分析中，以下哪个指标考虑了资金的时间价值？",
        "single", 2, "RK_XXXT_CH03",
        [
            {"code": "A", "content": "投资回收期（静态）", "value": 0},
            {"code": "B", "content": "净现值（NPV）", "value": 1},
            {"code": "C", "content": "投资利润率", "value": 0},
            {"code": "D", "content": "会计收益率", "value": 0},
        ],
        "B",
        "净现值（NPV）将未来现金流折现到当前，考虑了资金的时间价值。静态投资回收期、投资利润率和会计收益率都是静态指标，未考虑时间价值。"
    ),
    make_q(
        "RK_XXXT_CH03_Q03",
        "项目论证是指对项目的技术可行性和经济合理性进行分析和论证。",
        "judge", 1, "RK_XXXT_CH03",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "项目论证是项目立项前的重要环节，通过技术论证、经济论证和社会论证，为项目决策提供科学依据。"
    ),
    make_q(
        "RK_XXXT_CH03_Q04",
        "项目评估一般在项目论证之后进行，以下关于项目评估的描述，正确的是？",
        "single", 2, "RK_XXXT_CH03",
        [
            {"code": "A", "content": "项目评估由第三方机构进行，保证客观性", "value": 1},
            {"code": "B", "content": "项目评估由项目团队内部完成", "value": 0},
            {"code": "C", "content": "项目评估和项目论证是同一环节", "value": 0},
            {"code": "D", "content": "项目评估在项目立项之前不需要进行", "value": 0},
        ],
        "A",
        "项目评估通常由第三方或上级管理部门进行，对项目论证报告进行审查和评估，确保结论的客观公正。它与项目论证是先后两个不同环节。"
    ),
    make_q(
        "RK_XXXT_CH03_Q05",
        "在机会研究阶段，对项目投资估算的精度要求一般是？",
        "single", 2, "RK_XXXT_CH03",
        [
            {"code": "A", "content": "±10%", "value": 0},
            {"code": "B", "content": "±20%", "value": 0},
            {"code": "C", "content": "±30%", "value": 1},
            {"code": "D", "content": "±50%", "value": 0},
        ],
        "C",
        "机会研究阶段（投资机会鉴定）的估算精度一般为±30%；初步可行性研究为±20%；详细可行性研究为±10%。"
    ),

    # ===== 信息系统项目管理师 CH04 - 项目整体管理 =====
    make_q(
        "RK_XXXT_CH04_Q01",
        "项目章程的主要作用不包括以下哪项？",
        "single", 2, "RK_XXXT_CH04",
        [
            {"code": "A", "content": "正式确认项目的存在", "value": 0},
            {"code": "B", "content": "授权项目经理使用组织资源", "value": 0},
            {"code": "C", "content": "详细描述项目的所有技术方案", "value": 1},
            {"code": "D", "content": "将项目与组织战略目标联系起来", "value": 0},
        ],
        "C",
        "项目章程是项目正式启动的标志，授权项目经理，链接战略目标。但它不是技术文档，不会详细描述所有技术方案——技术方案属于项目管理计划范畴。",
        image="rk_xxxt_ch04_q01_charter",
        image_desc="项目章程包含的主要元素结构图",
        image_type="structure"
    ),
    make_q(
        "RK_XXXT_CH04_Q02",
        "以下关于整体变更控制的叙述中，正确的有？",
        "multiple", 2, "RK_XXXT_CH04",
        [
            {"code": "A", "content": "所有变更请求都必须经过变更控制委员会（CCB）审批", "value": 1},
            {"code": "B", "content": "变更控制委员会是项目团队的一个固定小组", "value": 0},
            {"code": "C", "content": "变更批准后需要更新项目管理计划", "value": 1},
            {"code": "D", "content": "被拒绝的变更请求也需要记录归档", "value": 1},
        ],
        "ACD",
        "所有变更须经CCB审批（A正确）；CCB可以是正式或非正式的，不一定是固定小组（B错误）；变更批准后需更新计划（C正确）；被拒绝的变更也应记录（D正确）。"
    ),
    make_q(
        "RK_XXXT_CH04_Q03",
        "项目管理计划是由项目经理单独制定的。",
        "judge", 1, "RK_XXXT_CH04",
        [
            {"code": "A", "content": "正确", "value": 0},
            {"code": "B", "content": "错误", "value": 1},
        ],
        "B",
        "项目管理计划应由项目经理主导，但需要项目团队成员和相关方共同参与制定，确保计划的可行性和各方认可。"
    ),
    make_q(
        "RK_XXXT_CH04_Q04",
        '在项目整体管理中，"指导与管理项目执行"过程组的主要输出是？',
        "single", 2, "RK_XXXT_CH04",
        [
            {"code": "A", "content": "项目管理计划", "value": 0},
            {"code": "B", "content": "可交付成果", "value": 1},
            {"code": "C", "content": "项目章程", "value": 0},
            {"code": "D", "content": "变更请求", "value": 0},
        ],
        "B",
        "指导与管理项目执行的主要输出是可交付成果和工作绩效数据。变更请求是执行过程中的一个输出，但不是主要输出。项目章程和项目管理计划是规划阶段的输出。"
    ),
    make_q(
        "RK_XXXT_CH04_Q05",
        "项目收尾过程包括以下哪些活动？",
        "multiple", 1, "RK_XXXT_CH04",
        [
            {"code": "A", "content": "确认所有工作已完成", "value": 1},
            {"code": "B", "content": "正式验收可交付成果", "value": 1},
            {"code": "C", "content": "总结经验教训并归档", "value": 1},
            {"code": "D", "content": "开始新的项目", "value": 0},
        ],
        "ABC",
        "项目收尾包括：确认工作完成、正式验收、经验教训总结归档、释放资源、关闭合同等。开始新项目不属于收尾活动。"
    ),

    # ===== 信息系统项目管理师 CH05 - 项目范围管理 =====
    make_q(
        "RK_XXXT_CH05_Q01",
        "WBS（工作分解结构）的最底层工作单元通常称为？",
        "single", 1, "RK_XXXT_CH05",
        [
            {"code": "A", "content": "里程碑", "value": 0},
            {"code": "B", "content": "工作包", "value": 1},
            {"code": "C", "content": "活动", "value": 0},
            {"code": "D", "content": "任务", "value": 0},
        ],
        "B",
        "WBS的最底层可交付成果称为工作包（Work Package）。活动是工作包的进一步分解，属于进度管理范畴。里程碑是项目中的关键检查点。",
        image="rk_xxxt_ch05_q01_wbs",
        image_desc="WBS分解结构示例图：项目→阶段→可交付成果→工作包",
        image_type="structure"
    ),
    make_q(
        "RK_XXXT_CH05_Q02",
        "以下关于范围定义和范围确认的叙述中，正确的有？",
        "multiple", 2, "RK_XXXT_CH05",
        [
            {"code": "A", "content": "范围定义是制定详细的项目范围说明书", "value": 1},
            {"code": "B", "content": "范围确认是正式验收已完成的可交付成果", "value": 1},
            {"code": "C", "content": "范围确认和质量控制是同一个过程", "value": 0},
            {"code": "D", "content": "范围定义的输出包含WBS", "value": 1},
        ],
        "ABD",
        '范围定义产出范围说明书和WBS（A、D正确）；范围确认是验收可交付成果（B正确）；范围确认关注"是否完成了"，质量控制关注"做得好不好"，不是同一过程（C错误）。'
    ),
    make_q(
        "RK_XXXT_CH05_Q03",
        "需求跟踪矩阵的主要作用是跟踪需求从提出到验证的全过程。",
        "judge", 1, "RK_XXXT_CH05",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "需求跟踪矩阵将需求与源头、WBS、设计、测试用例等关联，确保每个需求都被实现和验证，是范围管理的重要工具。"
    ),
    make_q(
        "RK_XXXT_CH05_Q04",
        "在项目范围控制中，以下哪项是最常用的工具？",
        "single", 2, "RK_XXXT_CH05",
        [
            {"code": "A", "content": "关键路径法", "value": 0},
            {"code": "B", "content": "偏差分析", "value": 1},
            {"code": "C", "content": "三点估算", "value": 0},
            {"code": "D", "content": "德尔菲技术", "value": 0},
        ],
        "B",
        "范围控制通过偏差分析比较实际范围与基准范围的差异，确定偏差原因并采取纠正措施。关键路径法属于进度管理，三点估算和德尔菲技术属于估算工具。"
    ),
    make_q(
        "RK_XXXT_CH05_Q05",
        "创建WBS时，分解的程度取决于以下哪个因素？",
        "single", 2, "RK_XXXT_CH05",
        [
            {"code": "A", "content": "项目经理的偏好", "value": 0},
            {"code": "B", "content": "工作包的大小和复杂度能够可靠估算和控制", "value": 1},
            {"code": "C", "content": "WBS的层级越多越好", "value": 0},
            {"code": "D", "content": "团队成员数量", "value": 0},
        ],
        "B",
        'WBS分解的粒度取决于工作包是否能被可靠地估算成本、工期和资源，并能够明确责任人。分解过细增加管理成本，分解过粗难以控制。一般遵循"8/80规则"（工作包工期8~80小时）。'
    ),

    # ===== 信息系统项目管理师 CH06 - 项目进度管理 =====
    make_q(
        "RK_XXXT_CH06_Q01",
        "在关键路径法（CPM）中，关键路径是项目网络图中什么路径？",
        "single", 1, "RK_XXXT_CH06",
        [
            {"code": "A", "content": "活动数最多的路径", "value": 0},
            {"code": "B", "content": "总工期最长的路径", "value": 1},
            {"code": "C", "content": "总工期最短的路径", "value": 0},
            {"code": "D", "content": "活动数最少的路径", "value": 0},
        ],
        "B",
        "关键路径是网络图中总工期最长的路径，决定了项目的最短完工时间。关键路径上的活动总时差为零，任何延误都会影响项目总工期。",
        image="rk_xxxt_ch06_q01_cpm",
        image_desc="项目网络图与关键路径示例，关键路径用红色标注，非关键路径显示总浮动时间",
        image_type="flowchart"
    ),
    make_q(
        "RK_XXXT_CH06_Q02",
        "以下关于进度压缩的叙述中，正确的有？",
        "multiple", 2, "RK_XXXT_CH06",
        [
            {"code": "A", "content": "赶工（Crashing）通过增加资源来缩短工期", "value": 1},
            {"code": "B", "content": "快速跟进（Fast Tracking）通过并行活动来缩短工期", "value": 1},
            {"code": "C", "content": "赶工不会增加项目成本", "value": 0},
            {"code": "D", "content": "快速跟进可能增加返工和风险", "value": 1},
        ],
        "ABD",
        "赶工通过追加资源缩短工期，通常增加成本（A正确，C错误）；快速跟进通过并行活动缩短工期，可能增加风险和返工（B、D正确）。"
    ),
    make_q(
        "RK_XXXT_CH06_Q03",
        "三点估算中的PERT技术使用的是哪种分布？",
        "single", 2, "RK_XXXT_CH06",
        [
            {"code": "A", "content": "均匀分布", "value": 0},
            {"code": "B", "content": "正态分布", "value": 0},
            {"code": "C", "content": "贝塔分布", "value": 1},
            {"code": "D", "content": "三角分布", "value": 0},
        ],
        "C",
        "PERT技术使用贝塔分布，估算公式为期望工期=(乐观+4×最可能+悲观)/6。三角分布公式为(乐观+最可能+悲观)/3，是另一种三点估算法。"
    ),
    make_q(
        "RK_XXXT_CH06_Q04",
        "甘特图是项目进度管理中最常用的可视化工具，能够清晰显示活动的开始和结束时间。",
        "judge", 1, "RK_XXXT_CH06",
        [
            {"code": "A", "content": "正确", "value": 1},
            {"code": "B", "content": "错误", "value": 0},
        ],
        "A",
        "甘特图以条形图形式展示项目活动的时间安排，直观显示每个活动的开始/结束时间、工期和进度，是进度管理中最常用的可视化工具。"
    ),
    make_q(
        "RK_XXXT_CH06_Q05",
        "某项目有活动A(3天)→B(5天)→C(2天)和活动A(3天)→D(4天)→E(3天)两条路径，则关键路径的总工期是？",
        "single", 2, "RK_XXXT_CH06",
        [
            {"code": "A", "content": "10天", "value": 1},
            {"code": "B", "content": "8天", "value": 0},
            {"code": "C", "content": "5天", "value": 0},
            {"code": "D", "content": "13天", "value": 0},
        ],
        "A",
        "路径A→B→C: 3+5+2=10天；路径A→D→E: 3+4+3=10天。两条路径工期相同（均为10天），都是关键路径。总工期为10天。",
        image="rk_xxxt_ch06_q05_network",
        image_desc="双路径项目网络图：A(3)→B(5)→C(2) 和 A(3)→D(4)→E(3)，两条路径工期均为10天",
        image_type="flowchart"
    ),
]


# ---------------------------------------------------------------------------
# 测试用例数据
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "_id": "TC_001",
        "name": "单选题作答-正确",
        "description": "用户在答题页面选择正确答案后提交，系统应判定为正确",
        "scenario": "习题作答",
        "questionId": "RK_RJJS_CH01_Q01",
        "input": {"userAnswer": ["C"]},
        "expected": {"correct": True, "score": 1},
        "precondition": "已进入软件设计师-计算机系统基础知识-第1题答题页面",
    },
    {
        "_id": "TC_002",
        "name": "单选题作答-错误",
        "description": "用户在答题页面选择错误答案后提交，系统应判定为错误",
        "scenario": "习题作答",
        "questionId": "RK_RJJS_CH01_Q01",
        "input": {"userAnswer": ["A"]},
        "expected": {"correct": False, "score": 0},
        "precondition": "已进入软件设计师-计算机系统基础知识-第1题答题页面",
    },
    {
        "_id": "TC_003",
        "name": "多选题作答-正确",
        "description": "用户选择所有正确选项（顺序无关）后提交，系统应判定为正确",
        "scenario": "习题作答",
        "questionId": "RK_RJJS_CH01_Q03",
        "input": {"userAnswer": ["A", "B", "D"]},
        "expected": {"correct": True, "score": 2},
        "precondition": "已进入软件设计师-计算机系统基础知识-第3题答题页面",
    },
    {
        "_id": "TC_004",
        "name": "多选题作答-部分正确",
        "description": "用户只选择部分正确选项后提交，系统应判定为错误",
        "scenario": "习题作答",
        "questionId": "RK_RJJS_CH01_Q03",
        "input": {"userAnswer": ["A", "B"]},
        "expected": {"correct": False, "score": 0},
        "precondition": "已进入软件设计师-计算机系统基础知识-第3题答题页面",
    },
    {
        "_id": "TC_005",
        "name": "判断题作答-正确",
        "description": "用户在判断题中选择正确选项后提交，系统应判定为正确",
        "scenario": "习题作答",
        "questionId": "RK_RJJS_CH01_Q04",
        "input": {"userAnswer": ["A"]},
        "expected": {"correct": True, "score": 1},
        "precondition": "已进入软件设计师-计算机系统基础知识-第4题答题页面",
    },
    {
        "_id": "TC_006",
        "name": "章节切换-软件设计师内部",
        "description": "用户在软件设计师科目内从第一章切换到第三章，题目列表应更新为第三章的题目",
        "scenario": "章节切换",
        "input": {"from": "RK_RJJS_CH01", "to": "RK_RJJS_CH03"},
        "expected": {"questionCount": 5, "firstQuestionId": "RK_RJJS_CH03_Q01"},
        "precondition": "已进入软件设计师科目答题页面",
    },
    {
        "_id": "TC_007",
        "name": "章节切换-信息系统项目管理师内部",
        "description": "用户在信息系统项目管理师科目内从第二章切换到第五章",
        "scenario": "章节切换",
        "input": {"from": "RK_XXXT_CH02", "to": "RK_XXXT_CH05"},
        "expected": {"questionCount": 5, "firstQuestionId": "RK_XXXT_CH05_Q01"},
        "precondition": "已进入信息系统项目管理师科目答题页面",
    },
    {
        "_id": "TC_008",
        "name": "科目切换-软件设计师到信息系统项目管理师",
        "description": "用户从软件设计师切换到信息系统项目管理师，科目信息和章节列表应更新",
        "scenario": "科目切换",
        "input": {"from": "RK_RJJS", "to": "RK_XXXT"},
        "expected": {
            "subjectName": "信息系统项目管理师",
            "chapterCount": 6,
            "firstChapterId": "RK_XXXT_CH01",
        },
        "precondition": "已进入软件设计师科目页面",
    },
    {
        "_id": "TC_009",
        "name": "科目切换-信息系统项目管理师到软件设计师",
        "description": "用户从信息系统项目管理师切换到软件设计师",
        "scenario": "科目切换",
        "input": {"from": "RK_XXXT", "to": "RK_RJJS"},
        "expected": {
            "subjectName": "软件设计师",
            "chapterCount": 6,
            "firstChapterId": "RK_RJJS_CH01",
        },
        "precondition": "已进入信息系统项目管理师科目页面",
    },
    {
        "_id": "TC_010",
        "name": "题型筛选-仅单选题",
        "description": "用户在答题页面选择仅显示单选题，系统应过滤出所有qtype=single的题目",
        "scenario": "题型筛选",
        "questionId": "RK_RJJS_CH01",
        "input": {"qtypeFilter": "single"},
        "expected": {"filteredCount": 3},
        "precondition": "已进入软件设计师-计算机系统基础知识答题页面",
    },
    {
        "_id": "TC_011",
        "name": "题型筛选-仅多选题",
        "description": "用户在答题页面选择仅显示多选题",
        "scenario": "题型筛选",
        "questionId": "RK_RJJS_CH01",
        "input": {"qtypeFilter": "multiple"},
        "expected": {"filteredCount": 1},
        "precondition": "已进入软件设计师-计算机系统基础知识答题页面",
    },
    {
        "_id": "TC_012",
        "name": "背题模式-显示答案解析",
        "description": "用户在背题模式下，页面应直接显示正确答案和解析，无需选择",
        "scenario": "答题模式",
        "questionId": "RK_RJJS_CH01_Q01",
        "input": {"mode": "memorize"},
        "expected": {
            "showAnswer": True,
            "answerText": "C",
            "explanationVisible": True,
        },
        "precondition": "已进入软件设计师-计算机系统基础知识-第1题背题模式页面",
    },
    {
        "_id": "TC_013",
        "name": "答题模式-隐藏答案",
        "description": "用户在答题模式下，页面不应直接显示正确答案，需要用户先作答",
        "scenario": "答题模式",
        "questionId": "RK_RJJS_CH01_Q01",
        "input": {"mode": "answer"},
        "expected": {
            "showAnswer": False,
            "answerText": "",
            "explanationVisible": False,
        },
        "precondition": "已进入软件设计师-计算机系统基础知识-第1题答题模式页面",
    },
    {
        "_id": "TC_014",
        "name": "配图题目渲染",
        "description": "包含image字段的题目，前端应显示图片描述和图片占位区域",
        "scenario": "配图渲染",
        "questionId": "RK_RJJS_CH02_Q02",
        "input": {},
        "expected": {
            "hasImage": True,
            "imageDesc": "表达式 a+b*(c-d) 对应的语法树，根节点为+，左子树为a，右子树为*（左b右-（左c右d））",
            "imageType": "structure",
        },
        "precondition": "已进入软件设计师-程序语言基础知识-第2题答题页面",
    },
    {
        "_id": "TC_015",
        "name": "空数据处理",
        "description": "当某章节无题目时，前端应显示友好的空数据提示",
        "scenario": "边界情况",
        "questionId": "",
        "input": {"examid": "RK_RJJS_CH99"},
        "expected": {"questionCount": 0, "emptyMessage": "暂无题目"},
        "precondition": "访问不存在的章节ID",
    },
]


# ---------------------------------------------------------------------------
# 软考数据的前缀，用于区分和清理
# ---------------------------------------------------------------------------
RK_PREFIX = "RK_"


class Command(BaseCommand):
    help = '导入软考（软件设计师/信息系统项目管理师）完整测试数据'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='清空所有集合后导入（含原有演示数据）')
        parser.add_argument('--append', action='store_true',
                            help='追加模式，不清理已有软考数据')

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = Document.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'已清空全部文档 {deleted} 条 (--reset)'))
        elif not options['append']:
            # 仅清理软考数据（RK_前缀的文档）
            rk_docs = Document.objects.filter(doc_id__startswith=RK_PREFIX)
            deleted = rk_docs.count()
            rk_docs.delete()
            self.stdout.write(self.style.WARNING(f'已清理旧软考数据 {deleted} 条'))

        total = 0

        # 1. 导入科目数据 → exam 集合
        for exam in EXAMS:
            doc_id = exam.pop('_id')
            Document.objects.update_or_create(
                collection='exam', doc_id=doc_id,
                defaults={'data': exam},
            )
            total += 1
        self.stdout.write(self.style.SUCCESS(f'exam       {len(EXAMS):>3} 条  (科目维度)'))

        # 2. 导入章节数据 → subjects 集合
        for subj in SUBJECTS:
            doc_id = subj.pop('_id')
            Document.objects.update_or_create(
                collection='subjects', doc_id=doc_id,
                defaults={'data': subj},
            )
            total += 1
        self.stdout.write(self.style.SUCCESS(f'subjects   {len(SUBJECTS):>3} 条  (章节维度)'))

        # 3. 导入习题数据 → questions 集合
        for q in QUESTIONS:
            doc_id = q.pop('_id')
            Document.objects.update_or_create(
                collection='questions', doc_id=doc_id,
                defaults={'data': q},
            )
            total += 1
        # 统计各题型数量
        type_counts = {}
        for q in QUESTIONS:
            t = q.get('qtype', 'unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
        type_str = ' / '.join(f'{k}:{v}' for k, v in sorted(type_counts.items()))
        self.stdout.write(self.style.SUCCESS(
            f'questions  {len(QUESTIONS):>3} 条  (习题数据, {type_str})'
        ))

        # 4. 导入测试用例 → testcases 集合
        for tc in TEST_CASES:
            doc_id = tc.pop('_id')
            Document.objects.update_or_create(
                collection='testcases', doc_id=doc_id,
                defaults={'data': tc},
            )
            total += 1
        self.stdout.write(self.style.SUCCESS(f'testcases  {len(TEST_CASES):>3} 条  (测试用例)'))

        # 5. 统计配图题目
        image_count = sum(1 for q in QUESTIONS if q.get('image'))
        self.stdout.write(self.style.SUCCESS(f'配图题目   {image_count:>3} 条'))

        self.stdout.write(self.style.SUCCESS(f'\n=== 完成，共导入 {total} 条文档 ==='))

        # 输出各科目统计
        self.stdout.write('\n--- 数据统计 ---')
        for exam in EXAMS:
            exam_id = f"RK_{'RJJS' if '软件设计师' in exam['name'] else 'XXXT'}"
            chapters = [s for s in SUBJECTS if s.get('pid') == exam_id]
            q_count = sum(1 for q in QUESTIONS if q.get('chapter', '').startswith(exam_id))
            self.stdout.write(
                f"  {exam['name']:<12} 章节:{len(chapters)}  题目:{q_count}  "
                f"配图:{sum(1 for q in QUESTIONS if q.get('chapter','').startswith(exam_id) and q.get('image'))}"
            )
