r"""
考试宝数据库清理与示例数据生成脚本

执行方式:
  cd backend
  python seed_data.py

功能:
  1. 按外键依赖逆序清除所有业务数据（不删表结构、不删 django_migrations）
  2. 按外键依赖正序插入真实合理的示例数据
  3. 覆盖系统主要业务场景：考试管理、题库、知识点、用户、答题记录、错题本、文章、知识库、管理后台
"""

import os
import sys
import json
import secrets
import random
from datetime import datetime, timedelta

# ---- Django 环境设置 ----
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.db import connection

from core.models import Document
from adminapi import article_code
from adminapi.models import (
    Role, AdminUser, AdminToken, OperationLog,
    Tag, QuestionTag, ImportJob,
)
from adminapi.permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSION_CODES


# ============================================================
#  第一部分：清除所有数据（按外键依赖逆序）
# ============================================================

def clear_all_data():
    """按外键依赖逆序清除所有业务数据。"""
    print("=" * 60)
    print("步骤 1：清除所有数据（按外键依赖逆序）")
    print("=" * 60)

    # 关闭外键约束检查期间，SQLite 也需要处理
    with connection.cursor() as cur:
        cur.execute("PRAGMA foreign_keys = OFF")

    # 清除顺序：叶子表 → 中间表 → 基础表
    clear_order = [
        # ---- 叶子表（有外键依赖其他表） ----
        ("adminapi_questiontag",   "题目标签绑定（FK→core_document, adminapi_tag）"),
        ("adminapi_admintoken",    "管理端令牌（FK→adminapi_adminuser）"),
        ("adminapi_operationlog",  "操作日志（FK→adminapi_adminuser, SET_NULL）"),
        ("adminapi_importjob",     "导入任务（FK→adminapi_adminuser, SET_NULL）"),
        # ---- 中间表 ----
        ("adminapi_adminuser",     "管理员账号（FK→adminapi_role）"),
        ("adminapi_tag",           "标签（无外键，但被 questiontag 引用）"),
        ("adminapi_role",          "角色（被 adminuser 引用，PROTECT）"),
        # ---- 基础表 ----
        ("core_document",          "通用文档（所有 collection 数据）"),
        # ---- Django 内部表 ----
        ("django_content_type",    "Django ContentType（可安全清除）"),
    ]

    for table_name, desc in clear_order:
        with connection.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            cur.execute(f"DELETE FROM {table_name}")
            print(f"  [清除] {table_name:30s} {count:5d} 行  ({desc})")

    # 重置 SQLite 自增序列
    with connection.cursor() as cur:
        cur.execute("DELETE FROM sqlite_sequence")
        print(f"  [重置] sqlite_sequence（自增序列归零）")

    with connection.cursor() as cur:
        cur.execute("PRAGMA foreign_keys = ON")

    print("  -> 所有数据已清除完成。\n")


# ============================================================
#  第二部分：生成示例数据（按外键依赖正序）
# ============================================================

def now_str():
    return timezone.now().strftime('%Y-%m-%d %H:%M:%S')

def create_doc(collection, doc_id, data):
    """创建 core_document 记录。"""
    doc = Document.objects.create(
        collection=collection,
        doc_id=doc_id,
        data=data,
    )
    return doc


def seed_roles():
    """生成 3 个内置角色。"""
    print("-" * 40)
    print("生成角色数据...")
    roles = {}
    role_defs = [
        ('superadmin', '超级管理员', '拥有系统全部权限，可管理所有模块'),
        ('operator',   '运营人员',   '负责题库管理、文章运营、用户管理等日常操作'),
        ('viewer',     '只读访客',   '仅可查看数据，不可执行任何写操作'),
    ]
    for code, name, desc in role_defs:
        role = Role.objects.create(
            code=code,
            name=name,
            description=desc,
            permissions=DEFAULT_ROLE_PERMISSIONS[code],
            is_system=True,
        )
        roles[code] = role
        print(f"  [角色] {code:12s} {name}  权限数={len(role.permissions)}")
    return roles


def seed_admin_users(roles):
    """生成管理员账号。"""
    print("-" * 40)
    print("生成管理员账号...")
    users = []
    admin_defs = [
        ('admin',      'admin123',     '超级管理员', roles['superadmin'], 'active'),
        ('operator01', 'operator123',  '张运营',     roles['operator'],   'active'),
        ('viewer01',   'viewer123',    '李访客',     roles['viewer'],     'active'),
        ('operator02', 'operator123',  '王编辑',     roles['operator'],   'disabled'),
    ]
    for username, pwd, nick, role, status in admin_defs:
        user = AdminUser.objects.create(
            username=username,
            password_hash=make_password(pwd),
            nickname=nick,
            role=role,
            status=status,
            last_login_at=timezone.now() - timedelta(hours=random.randint(1, 72)) if status == 'active' else None,
            last_login_ip=f'192.168.1.{random.randint(10, 200)}' if status == 'active' else '',
        )
        users.append(user)
        print(f"  [管理员] {username:12s} 昵称={nick:8s} 角色={role.code:12s} 状态={status}")
    return users


def seed_tags():
    """生成标签数据。"""
    print("-" * 40)
    print("生成标签数据...")
    tag_defs = [
        # (name, category, description, color)
        # 难度
        ('简单',   'difficulty', '基础难度，适合入门',     '#bfff40'),
        ('较易',   'difficulty', '略低于一般水平',         '#63b56b'),
        ('一般',   'difficulty', '标准考试难度',           '#409eff'),
        ('较难',   'difficulty', '需要综合理解',           '#f5cd07'),
        ('困难',   'difficulty', '高难度，易失分',         '#f01111'),
        # 知识点
        ('基础知识',   'knowledge', '考试核心基础概念',     '#909399'),
        ('进阶理解',   'knowledge', '需要深入理解的考点',   '#9c27b0'),
        ('易错点',     'knowledge', '历年高频错误点',       '#d9534f'),
        ('核心考点',   'knowledge', '必考知识点',           '#e6a23c'),
        ('高频考题',   'knowledge', '近三年出现频率高',     '#f56c6c'),
        # 题目类型
        ('单选题', 'qtype', '四选一',     '#4f7cff'),
        ('多选题', 'qtype', '多选',       '#8a63f2'),
        ('判断题', 'qtype', '正确/错误',  '#2f9ee0'),
        ('填空题', 'qtype', '填空',       '#1d9e75'),
        ('问答题', 'qtype', '简答',       '#d85a8a'),
        # 使用场景
        ('模拟考试', 'scene', '全真模拟',           '#4A90F3'),
        ('日常练习', 'scene', '日常刷题',           '#67C23A'),
        ('专项训练', 'scene', '专题突破',           '#E6A23C'),
    ]
    tags = {}
    for name, cat, desc, color in tag_defs:
        tag = Tag.objects.create(
            name=name,
            category=cat,
            description=desc,
            color=color,
        )
        tags[(name, cat)] = tag
        print(f"  [标签] {cat:12s} {name:8s} color={color}")
    return tags


def seed_core_data():
    """生成 core_document 各 collection 的示例数据。"""
    print("-" * 40)
    print("生成核心业务数据（core_document）...")

    question_docs = []  # 收集题目 Document 对象，后续绑定标签

    # ---- 1. AI 配置 ----
    create_doc('ai_config', 'ai-config', {
        "apiUrl": "https://api.openai.com/v1/chat/completions",
        "apiKey": "",
        "model": "gpt-4o-mini",
        "systemPrompt": "你是一个专业的备考文章写作助手，请根据用户给出的主题，撰写一篇结构清晰、内容充实的 Markdown 格式备考文章。",
        "temperature": 0.7,
        "maxTokens": 2000,
        "enabled": True,
    })
    print("  [ai_config] 1 条")

    # ---- 2. 考试定义 ----
    exams = [
        {
            "doc_id": "RK_RJJS",
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
            "doc_id": "RK_WLGL",
            "name": "网络管理员",
            "description": "全国计算机技术与软件专业技术资格（水平）考试 - 网络管理员（初级）",
            "duration": 120,
            "questionTypes": [
                {"type": "single", "label": "单选题", "count": 50, "score": 1},
                {"type": "multiple", "label": "多选题", "count": 10, "score": 2},
                {"type": "judge", "label": "判断题", "count": 10, "score": 1},
            ],
            "totalScore": 80,
            "passScore": 48,
            "category": "软考初级",
        },
    ]
    for ex in exams:
        create_doc('exam', ex["doc_id"], ex)
    print(f"  [exam] {len(exams)} 条")

    # ---- 3. 科目（章节） ----
    subjects_data = [
        # 软件设计师
        ("RK_RJJS_CH01", "RK_RJJS", "计算机系统基础知识", "计算机系统的组成、数据表示、校验码、CPU结构、存储系统、总线与中断等基础知识", 1,
         ["数制转换与编码", "校验码（奇偶/CRC）", "CPU组成与指令周期", "存储系统层次结构", "总线结构", "中断机制"]),
        ("RK_RJJS_CH02", "RK_RJJS", "程序语言基础", "编译与解释、数据类型、控制结构、函数调用、程序语言分类等", 2,
         ["编译与解释执行", "数据类型与作用域", "函数调用机制", "传值与传址"]),
        ("RK_RJJS_CH03", "RK_RJJS", "数据结构与算法", "线性表、栈队列、树、图、排序与查找算法", 3,
         ["线性表与链表", "栈与队列", "二叉树遍历", "排序算法比较", "图的基本概念"]),
        ("RK_RJJS_CH04", "RK_RJJS", "操作系统原理", "进程管理、内存管理、文件系统、设备管理、死锁", 4,
         ["进程调度算法", "内存分配策略", "死锁产生与预防", "文件系统结构"]),
        ("RK_RJJS_CH05", "RK_RJJS", "软件工程基础", "软件生命周期、需求分析、设计模式、测试方法、项目管理", 5,
         ["软件生命周期模型", "面向对象设计原则", "软件测试方法", "UML建模"]),
        # 网络管理员
        ("RK_WLGL_CH01", "RK_WLGL", "计算机网络概述", "OSI/TCP-IP模型、数据通信基础、传输介质", 1,
         ["OSI七层模型", "TCP/IP协议族", "数据传输方式", "传输介质与接口"]),
        ("RK_WLGL_CH02", "RK_WLGL", "局域网技术", "以太网、交换机原理、VLAN、STP", 2,
         ["以太网帧结构", "交换机工作原理", "VLAN配置", "生成树协议"]),
        ("RK_WLGL_CH03", "RK_WLGL", "网络互联与路由", "IP地址与子网划分、路由协议、NAT", 3,
         ["IP地址与子网掩码", "静态路由与动态路由", "RIP与OSPF", "NAT原理"]),
    ]
    for sid, pid, name, desc, weight, kps in subjects_data:
        create_doc('subjects', sid, {
            "name": name,
            "pid": pid,
            "description": desc,
            "knowledgePoints": kps,
            "sortWeight": weight,
        })
    print(f"  [subjects] {len(subjects_data)} 条")

    # ---- 4. 知识点 ----
    kp_data = [
        ("KP_RJJS_CH01", "计算机系统基础知识", "RK_RJJS", "RK_RJJS_CH01", 1,
         "计算机系统的组成、数据表示、校验码、CPU结构、存储系统、总线与中断等基础知识"),
        ("KP_RJJS_CH02", "程序语言基础", "RK_RJJS", "RK_RJJS_CH02", 1,
         "编译与解释、数据类型、控制结构、函数调用等基础概念"),
        ("KP_RJJS_CH03", "数据结构与算法", "RK_RJJS", "RK_RJJS_CH03", 1,
         "线性表、栈队列、树、图、排序与查找"),
        ("KP_RJJS_CH04", "操作系统原理", "RK_RJJS", "RK_RJJS_CH04", 1,
         "进程管理、内存管理、文件系统、设备管理"),
        ("KP_RJJS_CH05", "软件工程基础", "RK_RJJS", "RK_RJJS_CH05", 1,
         "软件生命周期、需求分析、设计模式、测试方法"),
        ("KP_WLGL_CH01", "计算机网络概述", "RK_WLGL", "RK_WLGL_CH01", 1,
         "OSI/TCP-IP模型、数据通信基础"),
        ("KP_WLGL_CH02", "局域网技术", "RK_WLGL", "RK_WLGL_CH02", 1,
         "以太网、交换机原理、VLAN"),
        ("KP_WLGL_CH03", "网络互联与路由", "RK_WLGL", "RK_WLGL_CH03", 1,
         "IP地址、路由协议、NAT"),
    ]
    for kpid, name, exam_id, subj_id, level, desc in kp_data:
        create_doc('knowledgepoints', kpid, {
            "name": name,
            "pid": exam_id,
            "examId": exam_id,
            "subjectId": subj_id,
            "level": level,
            "description": desc,
            "sortWeight": 1,
            "questionCount": random.randint(3, 8),
            "masteryCache": {
                "totalAnswered": random.randint(10, 50),
                "totalCorrect": random.randint(5, 30),
                "totalAttempts": random.randint(20, 80),
                "masteryRate": random.randint(30, 90),
                "level": random.choice(["weak", "fair", "good"]),
                "lastUpdated": now_str(),
            },
        })
    print(f"  [knowledgepoints] {len(kp_data)} 条")

    # ---- 5. 题目 ----
    questions_def = [
        # (doc_id, examid, chapter, qtype, typename, title, difficulty, answer, explanation, options, kp_ids, kp_names)
        # === 软件设计师 - 计算机系统基础知识 ===
        ("RK_RJJS_CH01_Q01", "RK_RJJS", "RK_RJJS_CH01", "single", "单选题",
         "在计算机中，以下哪种编码方式既能够表示正数和负数，又使得零的表示是唯一的？", 2, "C",
         "补码的零表示唯一（全0），而原码和反码的零有+0和-0两种表示。移码主要用于浮点数阶码表示。",
         [("A", "原码", False), ("B", "反码", False), ("C", "补码", True), ("D", "移码", False)],
         ["KP_RJJS_CH01"], ["计算机系统基础知识"]),

        ("RK_RJJS_CH01_Q02", "RK_RJJS", "RK_RJJS_CH01", "single", "单选题",
         "某计算机主存容量为4GB，按字节编址，地址寄存器至少需要多少位？", 2, "C",
         "4GB = 2^32 B，按字节编址需要32位地址线寻址。",
         [("A", "16位", False), ("B", "24位", False), ("C", "32位", True), ("D", "48位", False)],
         ["KP_RJJS_CH01"], ["计算机系统基础知识"]),

        ("RK_RJJS_CH01_Q03", "RK_RJJS", "RK_RJJS_CH01", "multiple", "多选题",
         "以下关于CRC循环冗余校验码的叙述中，正确的有？", 3, "ABD",
         "CRC是检错码不能纠错（C错误），能检测所有奇数个错误、双位错误及突发长度≤生成多项式长度的突发错误。",
         [("A", "CRC能够检测出所有奇数个错误", True), ("B", "CRC能够检测出所有双位错误", True),
          ("C", "CRC能够纠正错误", False), ("D", "CRC校验码的生成与多项式有关", True)],
         ["KP_RJJS_CH01"], ["计算机系统基础知识"]),

        ("RK_RJJS_CH01_Q04", "RK_RJJS", "RK_RJJS_CH01", "judge", "判断题",
         "Cache存储器是为了解决CPU与主存之间速度不匹配的问题而设置的。", 1, "A",
         "Cache利用程序局部性原理，在CPU和主存之间增加高速存储器，缓解速度差距。",
         [("A", "正确", True), ("B", "错误", False)],
         ["KP_RJJS_CH01"], ["计算机系统基础知识"]),

        ("RK_RJJS_CH01_Q05", "RK_RJJS", "RK_RJJS_CH01", "single", "单选题",
         "在浮点数表示中，保持什么不变可以保证浮点数的精度不丢失？", 3, "B",
         "浮点数规格化要求尾数最高位为有效位，保持尾数规格化可保证精度。",
         [("A", "阶码", False), ("B", "尾数规格化", True), ("C", "基数", False), ("D", "符号位", False)],
         ["KP_RJJS_CH01"], ["计算机系统基础知识"]),

        # === 软件设计师 - 程序语言基础 ===
        ("RK_RJJS_CH02_Q01", "RK_RJJS", "RK_RJJS_CH02", "single", "单选题",
         "编译程序和解释程序的根本区别在于？", 2, "B",
         "编译程序将源程序整体翻译成目标程序后执行，解释程序逐句翻译并执行，不生成目标程序。",
         [("A", "是否进行词法分析", False), ("B", "是否生成目标代码", True),
          ("C", "是否进行语法分析", False), ("D", "是否进行语义分析", False)],
         ["KP_RJJS_CH02"], ["程序语言基础"]),

        ("RK_RJJS_CH02_Q02", "RK_RJJS", "RK_RJJS_CH02", "judge", "判断题",
         "在C语言中，函数参数传递采用值传递方式，形参的改变不会影响实参。", 1, "A",
         "C语言函数参数默认为值传递，形参修改不影响实参（指针传递的本质也是值传递，传的是地址值）。",
         [("A", "正确", True), ("B", "错误", False)],
         ["KP_RJJS_CH02"], ["程序语言基础"]),

        # === 软件设计师 - 数据结构 ===
        ("RK_RJJS_CH03_Q01", "RK_RJJS", "RK_RJJS_CH03", "single", "单选题",
         "在长度为n的有序顺序表中进行二分查找，最坏情况下需要比较的次数为？", 2, "D",
         "二分查找最坏比较次数为 ⌊log₂(n)⌋ + 1。",
         [("A", "n", False), ("B", "n/2", False), ("C", "log₂(n)", False), ("D", "⌊log₂(n)⌋+1", True)],
         ["KP_RJJS_CH03"], ["数据结构与算法"]),

        ("RK_RJJS_CH03_Q02", "RK_RJJS", "RK_RJJS_CH03", "single", "单选题",
         "对n个元素进行快速排序，最坏情况下的时间复杂度为？", 2, "C",
         "快速排序最坏情况（每次划分极度不平衡）时间复杂度为O(n²)，平均为O(n log n)。",
         [("A", "O(n)", False), ("B", "O(n log n)", False), ("C", "O(n²)", True), ("D", "O(log n)", False)],
         ["KP_RJJS_CH03"], ["数据结构与算法"]),

        ("RK_RJJS_CH03_Q03", "RK_RJJS", "RK_RJJS_CH03", "multiple", "多选题",
         "以下哪些数据结构属于线性结构？", 1, "ABC",
         "栈、队列和链表都是线性结构，二叉树是非线性结构。",
         [("A", "栈", True), ("B", "队列", True), ("C", "链表", True), ("D", "二叉树", False)],
         ["KP_RJJS_CH03"], ["数据结构与算法"]),

        # === 软件设计师 - 操作系统 ===
        ("RK_RJJS_CH04_Q01", "RK_RJJS", "RK_RJJS_CH04", "single", "单选题",
         "在进程调度算法中，既有利于短作业又不会使长作业长期得不到执行的算法是？", 2, "C",
         "高响应比优先调度算法通过响应比 = (等待时间 + 要求服务时间) / 要求服务时间，兼顾短作业和长作业。",
         [("A", "先来先服务FCFS", False), ("B", "短作业优先SJF", False),
          ("C", "高响应比优先", True), ("D", "时间片轮转RR", False)],
         ["KP_RJJS_CH04"], ["操作系统原理"]),

        ("RK_RJJS_CH04_Q02", "RK_RJJS", "RK_RJJS_CH04", "judge", "判断题",
         "死锁的四个必要条件是：互斥、请求保持、不剥夺和环路等待。破坏其中任一条件即可预防死锁。", 2, "A",
         "死锁必要条件为互斥、请求和保持、不剥夺、环路等待，破坏任一条件即可预防死锁。",
         [("A", "正确", True), ("B", "错误", False)],
         ["KP_RJJS_CH04"], ["操作系统原理"]),

        # === 软件设计师 - 软件工程 ===
        ("RK_RJJS_CH05_Q01", "RK_RJJS", "RK_RJJS_CH05", "single", "单选题",
         "在软件测试中，发现错误能力最强的测试方法是？", 2, "B",
         '白盒测试了解程序内部结构，能发现代码逻辑错误；但"发现错误能力最强"通常指黑盒测试中的边界值分析等方法。从选项看因果图法适合发现组合条件错误。',
         [("A", "等价类划分", False), ("B", "边界值分析", True),
          ("C", "因果图法", False), ("D", "错误推测法", False)],
         ["KP_RJJS_CH05"], ["软件工程基础"]),

        ("RK_RJJS_CH05_Q02", "RK_RJJS", "RK_RJJS_CH05", "single", "单选题",
         '面向对象设计中，"开闭原则"的含义是？', 3, "A",
         "开闭原则：软件实体应对扩展开放，对修改关闭。",
         [("A", "对扩展开放，对修改关闭", True), ("B", "对修改开放，对扩展关闭", False),
          ("C", "同时开放扩展和修改", False), ("D", "同时关闭扩展和修改", False)],
         ["KP_RJJS_CH05"], ["软件工程基础"]),

        ("RK_RJJS_CH05_Q03", "RK_RJJS", "RK_RJJS_CH05", "judge", "判断题",
         "瀑布模型要求每个阶段完成后才能进入下一阶段，不支持回溯。", 1, "A",
         "瀑布模型是线性顺序模型，严格按阶段推进，文档驱动，不支持逆向回溯。",
         [("A", "正确", True), ("B", "错误", False)],
         ["KP_RJJS_CH05"], ["软件工程基础"]),

        # === 网络管理员 - 计算机网络概述 ===
        ("RK_WLGL_CH01_Q01", "RK_WLGL", "RK_WLGL_CH01", "single", "单选题",
         "在OSI参考模型中，负责数据加密和解密的层是？", 2, "C",
         "OSI表示层负责数据格式转换、加密解密和数据压缩。",
         [("A", "应用层", False), ("B", "会话层", False), ("C", "表示层", True), ("D", "传输层", False)],
         ["KP_WLGL_CH01"], ["计算机网络概述"]),

        ("RK_WLGL_CH01_Q02", "RK_WLGL", "RK_WLGL_CH01", "single", "单选题",
         "TCP协议工作在OSI模型的哪一层？", 1, "C",
         "TCP是传输层协议，提供面向连接的可靠字节流传输服务。",
         [("A", "网络层", False), ("B", "数据链路层", False), ("C", "传输层", True), ("D", "应用层", False)],
         ["KP_WLGL_CH01"], ["计算机网络概述"]),

        # === 网络管理员 - 局域网 ===
        ("RK_WLGL_CH02_Q01", "RK_WLGL", "RK_WLGL_CH02", "single", "单选题",
         "以太网采用的介质访问控制协议是？", 2, "B",
         "以太网使用CSMA/CD（载波监听多路访问/冲突检测）协议。",
         [("A", "CSMA/CA", False), ("B", "CSMA/CD", True), ("C", "Token Ring", False), ("D", "TDMA", False)],
         ["KP_WLGL_CH02"], ["局域网技术"]),

        ("RK_WLGL_CH02_Q02", "RK_WLGL", "RK_WLGL_CH02", "judge", "判断题",
         "VLAN技术通过在交换机上划分广播域，可以有效隔离广播风暴。", 1, "A",
         "VLAN将一个物理局域网划分为多个逻辑广播域，隔离广播流量。",
         [("A", "正确", True), ("B", "错误", False)],
         ["KP_WLGL_CH02"], ["局域网技术"]),

        # === 网络管理员 - 路由 ===
        ("RK_WLGL_CH03_Q01", "RK_WLGL", "RK_WLGL_CH03", "single", "单选题",
         "IP地址192.168.1.100/26所在的子网网络地址是？", 3, "C",
         "/26掩码为255.255.255.192，192.168.1.100在子网192.168.1.64/26内，网络地址为192.168.1.64。",
         [("A", "192.168.1.0", False), ("B", "192.168.1.32", False),
          ("C", "192.168.1.64", True), ("D", "192.168.1.128", False)],
         ["KP_WLGL_CH03"], ["网络互联与路由"]),

        ("RK_WLGL_CH03_Q02", "RK_WLGL", "RK_WLGL_CH03", "multiple", "多选题",
         "以下哪些是动态路由协议？", 2, "BCD",
         "静态路由是手动配置的，RIP、OSPF、BGP都是动态路由协议。",
         [("A", "静态路由", False), ("B", "RIP", True), ("C", "OSPF", True), ("D", "BGP", True)],
         ["KP_WLGL_CH03"], ["网络互联与路由"]),
    ]

    for q in questions_def:
        (doc_id, examid, chapter, qtype, typename, title, diff, answer,
         explanation, opts, kp_ids, kp_names) = q

        options_data = []
        for code, content, is_correct in opts:
            opt = {"code": code, "content": content}
            if qtype == "multiple":
                opt["value"] = 1 if is_correct else 0
            elif qtype == "judge":
                opt["value"] = 1 if is_correct else 0
            else:  # single
                opt["is_correct"] = is_correct
                opt["value"] = "1" if is_correct else "0"
            options_data.append(opt)

        doc = create_doc('questions', doc_id, {
            "title": title,
            "qtype": qtype,
            "type": qtype,
            "typename": typename,
            "typecode": qtype,
            "difficulty": diff,
            "examid": examid,
            "chapter": chapter,
            "answer": answer,
            "explanation": explanation,
            "comments": explanation,
            "options": options_data,
            "knowledgePointIds": kp_ids,
            "knowledgePointNames": kp_names,
        })
        question_docs.append(doc)

    print(f"  [questions] {len(questions_def)} 条")

    # ---- 6. 知识库（教材章节） ----
    kb_data = [
        ("KB_RJJS_01", "软件设计师教程 - 第1章 计算机系统基础知识", "textbook", "软件设计师",
         "涵盖计算机硬件组成、数据表示、校验码、CPU结构、指令系统、总线与I/O等核心内容", 15, 100,
         "BK_RJJS", "软件设计师教程", 1, "计算机系统基础知识"),
        ("KB_RJJS_03", "软件设计师教程 - 第3章 数据结构与算法", "textbook", "软件设计师",
         "线性表、栈队列、树、图、排序与查找算法的原理与实现", 20, 80,
         "BK_RJJS", "软件设计师教程", 3, "数据结构与算法"),
        ("KB_RJJS_04", "软件设计师教程 - 第4章 操作系统原理", "textbook", "软件设计师",
         "进程管理、内存管理、文件系统、设备管理、死锁处理", 18, 70,
         "BK_RJJS", "软件设计师教程", 4, "操作系统原理"),
        ("KB_WLGL_01", "网络管理员教程 - 第1章 计算机网络概述", "textbook", "网络管理员",
         "OSI/TCP-IP模型、数据通信基础、传输介质与网络设备", 12, 100,
         "BK_WLGL", "网络管理员教程", 1, "计算机网络概述"),
        ("KB_WLGL_02", "网络管理员教程 - 第2章 局域网技术", "textbook", "网络管理员",
         "以太网原理、交换机配置、VLAN与STP、无线局域网", 14, 90,
         "BK_WLGL", "网络管理员教程", 2, "局域网技术"),
        ("KB_WLGL_03", "网络管理员教程 - 第3章 网络互联与路由", "textbook", "网络管理员",
         "IP地址与子网划分、静态与动态路由、RIP/OSPF、NAT原理", 16, 85,
         "BK_WLGL", "网络管理员教程", 3, "网络互联与路由"),
        ("KB_RJJS_05", "软件设计师教程 - 第5章 软件工程基础", "textbook", "软件设计师",
         "软件生命周期、开发模型、需求分析、UML建模、测试方法与项目管理", 16, 65,
         "BK_RJJS", "软件设计师教程", 5, "软件工程基础"),
        ("KB_RJJS_SM_01", "软件工程核心考点精要总结", "summary", "软件设计师",
         "软件生命周期、开发模型、需求分析、面向对象、测试方法等高频考点整理", 8, 85,
         "", "", 0, ""),
        ("KB_RJJS_QR_01", "高频选择题速记口诀50条", "quickref", "软件设计师",
         "覆盖计算机基础、数据结构、软件工程、网络协议的高频考点速记口诀", 3, 75,
         "", "", 0, ""),
    ]
    for kid, title, ktype, cat, summary, pages, weight, book_id, book_title, ch_no, ch_title in kb_data:
        payload = {
            "title": title,
            "type": ktype,
            "category": cat,
            "summary": summary,
            "pages": pages,
            "sortWeight": weight,
            # 正文摘要：让 RAG 索引能够按内容命中该条目（而不仅靠标题）
            "content": "%s\n\n本章重点：%s。建议结合历年真题练习巩固。" % (summary, ch_title or title),
        }
        if book_id:
            payload.update({
                "bookId": book_id,
                "bookTitle": book_title,
                "chapterNo": ch_no,
                "chapterTitle": ch_title,
            })
        if ch_no:
            payload["toc"] = [
                {"title": f"{ch_no}.1 概述", "page": 1, "level": 1,
                 "children": [{"title": f"{ch_no}.1.1 基本概念", "page": 2, "level": 2}]},
                {"title": f"{ch_no}.2 详细内容", "page": 5, "level": 1,
                 "children": [{"title": f"{ch_no}.2.1 核心原理", "page": 6, "level": 2}]},
                {"title": f"{ch_no}.3 小结与习题", "page": pages - 2, "level": 1},
            ]
        create_doc('knowledgebase', kid, payload)
    print(f"  [knowledgebase] {len(kb_data)} 条")

    # ---- 7. 用户档案（profiles） ----
    nicknames = [
        ("张明", "北京", "北京"), ("李芳", "上海", "上海"), ("王强", "广东", "深圳"),
        ("赵敏", "四川", "成都"), ("刘洋", "湖北", "武汉"), ("陈静", "浙江", "杭州"),
        ("杨帆", "江苏", "南京"), ("黄磊", "山东", "青岛"), ("周婷", "陕西", "西安"),
        ("吴昊", "福建", "厦门"),
    ]
    for i, (nick, prov, city) in enumerate(nicknames):
        openid = f"oDWYj0User{i:03d}abcdef1234567890"
        create_doc('profiles', f"profile_{i+1:03d}", {
            "userInfo": {
                "nickName": nick,
                "gender": random.choice([0, 1, 1, 2]),
                "language": "zh_CN",
                "city": city,
                "province": prov,
                "country": "中国",
                "avatarUrl": "/images/header.png",
            },
            "_openid": openid,
            # 前 3 个演示用户标记为 VIP，可使用 AI 解析功能
            "vip": i < 3,
        })
    print(f"  [profiles] {len(nicknames)} 条")

    # ---- 8. 答题记录（historys） ----
    # 数据结构与小程序答题页写入保持一致：
    #   items    = [题目 doc_id, ...]（字符串数组）
    #   score_arr= [[用户所选选项码], ...]（与 items 下标对齐）
    #   rightNum = 答对题数；nums/total = 题量
    # 同时写入 AI 模块需要的 examid（= 考试 doc_id）与 subject（科目名）。
    # 数量保证：
    #   - 试卷分析（ExamAnalysisService）要求单考试 >= 10 份记录
    #   - 答题分析 / 学习报告（LearningProfileService / LearningReportService）
    #     要求单用户 >= 20 条、周期内 >= 5 条
    exam_name_map = {ex["doc_id"]: ex["name"] for ex in exams}
    exam_total_map = {ex["doc_id"]: ex.get("totalScore", 100) for ex in exams}
    history_count = 0
    for user_idx in range(6):
        openid = f"oDWYj0User{user_idx:03d}abcdef1234567890"
        for hist_idx in range(22):
            num_qs = random.randint(4, 6)
            qs_list = random.sample(questions_def, min(num_qs, len(questions_def)))
            items_ids = []
            score_arr = []
            total_right = 0
            for q in qs_list:
                (doc_id, examid, chapter, qtype, typename, title, diff, answer,
                 explanation, opts, kp_ids, kp_names) = q
                correct_codes = sorted(o[0] for o in opts if o[2])
                # 约 65% 概率答对，其余给出一个典型错误作答
                if random.random() < 0.65:
                    picked = correct_codes
                elif qtype == "multiple":
                    picked = correct_codes[:max(1, len(correct_codes) - 1)] or correct_codes
                else:
                    wrong_codes = [o[0] for o in opts if not o[2]]
                    picked = [random.choice(wrong_codes)] if wrong_codes else correct_codes
                if picked == correct_codes:
                    total_right += 1
                items_ids.append(doc_id)
                score_arr.append(picked)

            exam_id = qs_list[0][1]
            hist_id = f"hist_user{user_idx+1}_{hist_idx+1:03d}"
            exam_total = exam_total_map.get(exam_id, 100)
            create_doc('historys', hist_id, {
                "_openid": openid,
                "subject": {"_id": exam_id, "name": exam_name_map.get(exam_id, '')},
                "examid": exam_id,
                "time": f"{random.randint(0, 5)}:{random.randint(10, 59):02d}",
                "items": items_ids,
                "score_arr": score_arr,
                "rightNum": total_right,
                "nums": len(qs_list),
                "score": round(total_right / len(qs_list) * exam_total, 1),
                "total": len(qs_list),
                "createTime": (timezone.now() - timedelta(days=random.randint(0, 25))).strftime('%Y/%m/%d %H:%M'),
            })
            history_count += 1
    print(f"  [historys] {history_count} 条")

    # ---- 9. 错题本（notes） ----
    note_count = 0
    for user_idx in range(4):
        openid = f"oDWYj0User{user_idx:03d}abcdef1234567890"
        for note_idx in range(4):
            q = random.choice(questions_def)
            (doc_id, examid, chapter, qtype, typename, title, diff, answer,
             explanation, opts, kp_ids, kp_names) = q

            # 生成一个错误的选项选择
            wrong_opts = [o for o in opts if not o[2]]
            if wrong_opts:
                wrong_code = wrong_opts[0][0]
            else:
                wrong_code = "A"

            options_note = []
            for code, content, is_correct in opts:
                options_note.append({
                    "code": code,
                    "content": content,
                    "value": "1" if is_correct else "0",
                    "selected": code == wrong_code,
                })

            note_id = f"note_user{user_idx+1}_{note_idx+1:03d}"
            create_doc('notes', note_id, {
                "_openid": openid,
                "ordernum": f"2026091{user_idx}{note_idx}0000",
                "question": {
                    "_id": doc_id,
                    "title": title,
                    "typecode": qtype,
                    "typename": typename,
                    "comments": explanation,
                    "options": options_note,
                    "index": float(note_idx),
                    "status": False,
                    "right": 0.0,
                    "selected": True,
                },
                "note": f"这道题容易混淆{kp_names[0]}的概念，需要重点复习。",
                "category": kp_names[0],
                "resolved": False,
                "retryCount": random.randint(0, 3),
                "reviewStatus": "pending",
                "addTime": (timezone.now() - timedelta(days=random.randint(0, 20))).strftime('%Y/%m/%d %H:%M'),
            })
            note_count += 1
    print(f"  [notes] {note_count} 条")

    # ---- 10. 文章 ----
    articles_def = [
        ("art-001", "高效刷题的五个方法，助你轻松备考", "published",
         "盲目刷题不如精准刷题，掌握正确的方法可以让复习效率翻倍。",
         "盲目刷题不如精准刷题。第一个方法是错题优先：把错题本里的题目反复做三遍，比做三十道新题更有价值。\n\n第二个方法是限时训练，模拟真实考试节奏，训练答题速度与心态。\n\n第三个方法是专题突破，针对薄弱题型集中练习，逐个击破。\n\n第四个方法是睡前回顾，利用记忆黄金期复习当天错题。\n\n第五个方法是定期模拟，每周一次完整模拟考，检验阶段成果。",
         ["备考技巧", "刷题方法", "高效学习"], 1024),
        ("art-002", "软考中级软件设计师备考指南", "published",
         "从考试大纲到复习规划，全面解析软件设计师考试的通关策略。",
         "## 考试概况\n\n软件设计师属于软考中级，每年5月和11月各考一次。\n\n## 复习规划\n\n### 第一阶段：基础学习（1-2月）\n通读教材，建立知识框架。\n\n### 第二阶段：专题强化（1月）\n按章节刷题，攻克薄弱环节。\n\n### 第三阶段：冲刺模拟（2周）\n历年真题模拟，查漏补缺。\n\n## 重点章节\n\n- 计算机系统基础知识\n- 数据结构与算法\n- 软件工程\n- UML建模",
         ["软考", "软件设计师", "备考指南"], 856),
        ("art-003", "操作系统死锁问题详解", "published",
         "深入理解死锁的四个必要条件及预防策略，掌握考试高频考点。",
         "## 死锁的定义\n\n死锁是指两个或两个以上的进程在执行过程中，因争夺资源而造成的一种互相等待的现象。\n\n## 四个必要条件\n\n1. **互斥条件**：资源一次只能被一个进程使用\n2. **请求和保持**：进程已获得资源但又被阻塞等待新资源\n3. **不剥夺条件**：已获得的资源不能被强行剥夺\n4. **环路等待**：存在进程-资源的循环等待链\n\n## 预防策略\n\n- 破坏互斥：资源共享\n- 破坏请求保持：预先分配\n- 破坏不剥夺：允许抢占\n- 破坏环路等待：顺序分配",
         ["操作系统", "死锁", "高频考点"], 432),
        ("art-004", "网络管理员考试核心知识点串讲", "pending",
         "系统梳理网络管理员考试的核心知识点，帮助考生快速把握重点。",
         "本文正在审核中...",
         ["网络管理员", "软考"], 0),
        ("art-005", "数据结构之排序算法对比分析", "published",
         "对比分析各种排序算法的时间复杂度、空间复杂度和稳定性，考试必背知识点。",
         '## 排序算法对比\n\n| 算法 | 平均时间 | 最坏时间 | 空间 | 稳定性 |\n|------|---------|---------|------|--------|\n| 冒泡 | O(n²) | O(n²) | O(1) | 稳定 |\n| 选择 | O(n²) | O(n²) | O(1) | 不稳定 |\n| 插入 | O(n²) | O(n²) | O(1) | 稳定 |\n| 快排 | O(n log n) | O(n²) | O(log n) | 不稳定 |\n| 归并 | O(n log n) | O(n log n) | O(n) | 稳定 |\n| 堆排 | O(n log n) | O(n log n) | O(1) | 不稳定 |\n\n## 记忆技巧\n\n- 稳定的排序：冒泡、插入、归并（"冒插归"稳）\n- 不稳定的排序：选择、快排、堆排（"选快堆"不稳）',
         ["数据结构", "排序算法", "高频考点"], 689),
    ]
    article_docs = []
    for aid, title, status, summary, content, tags, views in articles_def:
        doc = create_doc('articles', aid, {
            "_id": aid,
            "title": title,
            "summary": summary,
            "content": content,
            "cover": "",
            "images": [],
            "tags": tags,
            "status": status,
            "author": "考试宝",
            "views": views,
            "createTime": (timezone.now() - timedelta(days=random.randint(1, 30))).strftime('%Y/%m/%d %H:%M'),
            "updateTime": now_str(),
        })
        # 统一生成唯一编码 ART-YYYYMMDD-NNNN（供知识库索引溯源）
        article_code.assign_article_code(doc)
        article_docs.append(doc)
    print(f"  [articles] {len(articles_def)} 条")

    # ---- 10.1 文章 -> 知识库索引（示范可追溯关联） ----
    # 仅取已发布文章，生成 _id = KB_ART_<编码> 的知识库条目，
    # 使 AI 知识库问答可直接引用文章内容，并可反查来源文章编码。
    from adminapi.ai_services import KnowledgeRAGService
    linked = []
    for doc in article_docs:
        if (doc.data or {}).get('status') != 'published':
            continue
        result = KnowledgeRAGService.add_article_to_index(doc, operator='seed')
        if result and not result.get('error'):
            linked.append(result['article_code'])
        if len(linked) >= 2:
            break
    print(f"  [article->knowledgebase] {len(linked)} 篇：{', '.join(linked)}")

    # ---- 11. 测试用例 ----
    testcases_def = [
        ("TC_001", "单选题作答-正确", "习题作答", "RK_RJJS_CH01_Q01",
         "用户在答题页面选择正确答案后提交", "已进入软件设计师-计算机系统基础知识-第1题答题页面",
         {"userAnswer": ["C"]}, {"correct": True, "score": 1}),
        ("TC_002", "单选题作答-错误", "习题作答", "RK_RJJS_CH01_Q01",
         "用户在答题页面选择错误答案后提交", "已进入软件设计师-计算机系统基础知识-第1题答题页面",
         {"userAnswer": ["A"]}, {"correct": False, "score": 0}),
        ("TC_003", "多选题作答-全对", "习题作答", "RK_RJJS_CH01_Q03",
         "用户选择所有正确选项", "已进入多选题作答页面",
         {"userAnswer": ["A", "B", "D"]}, {"correct": True, "score": 2}),
        ("TC_004", "多选题作答-部分对", "习题作答", "RK_RJJS_CH01_Q03",
         "用户选择部分正确选项", "已进入多选题作答页面",
         {"userAnswer": ["A", "B"]}, {"correct": False, "score": 0}),
        ("TC_005", "判断题作答-正确", "习题作答", "RK_RJJS_CH01_Q04",
         "用户选择正确判断", "已进入判断题作答页面",
         {"userAnswer": ["A"]}, {"correct": True, "score": 1}),
        ("TC_006", "模拟考试-完成提交", "模拟考试", "RK_RJJS",
         "用户完成模拟考试全部题目并提交", "已进入软件设计师模拟考试",
         {"totalQuestions": 5, "answered": 5, "submit": True},
         {"submitted": True, "graded": True}),
        ("TC_007", "错题本-添加错题", "错题本", "RK_RJJS_CH02_Q01",
         "用户答错后系统自动加入错题本", "用户刚答错一道题",
         {"questionId": "RK_RJJS_CH02_Q01", "action": "add"},
         {"added": True}),
        ("TC_008", "知识点掌握度更新", "知识点分析", "KP_RJJS_CH01",
         "用户答完题目后系统更新知识点掌握度", "用户完成计算机系统基础知识相关题目",
         {"knowledgePointId": "KP_RJJS_CH01", "answered": 5, "correct": 3},
         {"masteryRate": 60, "level": "fair"}),
    ]
    for tcid, name, scenario, qid, desc, precond, inp, expected in testcases_def:
        create_doc('testcases', tcid, {
            "name": name,
            "description": desc,
            "scenario": scenario,
            "questionId": qid,
            "input": inp,
            "expected": expected,
            "precondition": precond,
        })
    print(f"  [testcases] {len(testcases_def)} 条")

    return question_docs


def seed_question_tags(question_docs, tags):
    """为题目绑定标签。"""
    print("-" * 40)
    print("生成题目标签绑定...")

    # 根据 qtype 绑定类型标签
    qtype_tag_map = {
        "single": ("单选题", "qtype"),
        "multiple": ("多选题", "qtype"),
        "judge": ("判断题", "qtype"),
    }

    # 根据 difficulty 绑定难度标签
    diff_tag_map = {
        1: ("简单", "difficulty"),
        2: ("一般", "difficulty"),
        3: ("较难", "difficulty"),
    }

    count = 0
    for doc in question_docs:
        data = doc.data
        qtype = data.get("qtype", "single")
        diff = data.get("difficulty", 2)

        # 绑定类型标签
        if qtype in qtype_tag_map:
            tag_key = qtype_tag_map[qtype]
            if tag_key in tags:
                QuestionTag.objects.create(question=doc, tag=tags[tag_key])
                count += 1

        # 绑定难度标签
        if diff in diff_tag_map:
            tag_key = diff_tag_map[diff]
            if tag_key in tags:
                QuestionTag.objects.create(question=doc, tag=tags[tag_key])
                count += 1

        # 绑定知识点标签（随机）
        kp_tag = random.choice([("基础知识", "knowledge"), ("核心考点", "knowledge"), ("高频考题", "knowledge")])
        if kp_tag in tags:
            QuestionTag.objects.create(question=doc, tag=tags[kp_tag])
            count += 1

    print(f"  [questiontag] {count} 条绑定关系")


def seed_import_jobs(admin_users):
    """生成导入任务记录。"""
    print("-" * 40)
    print("生成导入任务记录...")

    import_jobs_def = [
        ("success", "sync", 20, 20, 0, 0, "批量导入软件设计师CH01题目"),
        ("partial", "async", 15, 12, 2, 1, "导入网络管理员题目（部分重复跳过）"),
        ("failed", "async", 10, 0, 10, 0, "导入数据格式错误，全部失败"),
    ]

    for i, (status, mode, total, succ, fail, skip, desc) in enumerate(import_jobs_def):
        created_by = admin_users[0] if i < 2 else admin_users[1]
        job = ImportJob.objects.create(
            created_by=created_by,
            mode=mode,
            status=status,
            total=total,
            succeeded=succ,
            failed=fail,
            skipped=skip,
            payload={"source": "excel", "description": desc},
            results=[
                {"index": j+1, "status": "success" if j < succ else "failed", "title": f"题目{j+1}"}
                for j in range(min(total, 5))
            ],
            error="" if status != "failed" else "Excel格式不正确：缺少title列",
            started_at=timezone.now() - timedelta(hours=i+1),
            finished_at=timezone.now() - timedelta(hours=i, minutes=30) if status != "processing" else None,
        )
        print(f"  [importjob] #{job.pk} status={status:10s} total={total} succeeded={succ}")

    print(f"  共 {len(import_jobs_def)} 条")


def seed_operation_logs(admin_users):
    """生成操作审计日志。"""
    print("-" * 40)
    print("生成操作日志...")

    log_defs = [
        ("login",         "",                    "管理员登录"),
        ("question.create", "RK_RJJS_CH01_Q01",  "创建题目：计算机系统基础知识-补码"),
        ("question.create", "RK_RJJS_CH01_Q02",  "创建题目：主存容量计算"),
        ("subject.create",  "RK_RJJS_CH05",      "创建科目：软件工程基础"),
        ("subject.update",  "RK_RJJS_CH03",      "更新科目描述：数据结构与算法"),
        ("exam.view",       "RK_RJJS",           "查看考试：软件设计师"),
        ("tag.create",      "高频考题",            "创建标签：高频考题(knowledge)"),
        ("tag.bind",        "RK_RJJS_CH01_Q01",  "绑定标签到题目"),
        ("article.create",  "art-001",           "创建文章：高效刷题的五个方法"),
        ("article.audit",   "art-002",           "审核通过文章：软考中级备考指南"),
        ("article.audit",   "art-004",           "文章待审核：网络管理员核心知识点"),
        ("user.view",       "",                  "查看小程序用户列表"),
        ("user.update",     "profile_003",       "更新用户信息"),
        ("ai.config",       "ai-config",         "更新AI配置：修改模型为gpt-4o-mini"),
        ("admin.create",    "operator01",        "创建管理员账号：operator01"),
        ("admin.update",    "viewer01",          "更新管理员：重置密码"),
        ("import.start",    "1",                 "启动批量导入任务"),
        ("import.finish",   "1",                 "批量导入完成：成功20题"),
        ("knowledge.create", "KP_RJJS_CH05",     "创建知识点：软件工程基础"),
        ("knowledge.update", "KP_RJJS_CH01",     "更新知识点掌握度缓存"),
    ]

    for i, (action, target, detail) in enumerate(log_defs):
        user = admin_users[0] if i % 3 != 2 else admin_users[1]
        OperationLog.objects.create(
            user=user,
            username=user.username,
            action=action,
            target=target,
            detail=detail,
            ip=f"192.168.1.{100 + i % 50}",
        )

    print(f"  [operationlog] {len(log_defs)} 条")


def seed_admin_tokens(admin_users):
    """为活跃管理员生成登录令牌。"""
    print("-" * 40)
    print("生成管理员令牌...")

    for user in admin_users[:2]:  # 只为前两个活跃用户生成
        token = AdminToken.objects.create(
            token=secrets.token_hex(32),
            user=user,
            expires_at=timezone.now() + timedelta(hours=12),
        )
        print(f"  [admintoken] user={user.username:12s} token={token.token[:16]}...")

    print(f"  共 2 条")


def verify_data():
    """验证数据完整性。"""
    print("=" * 60)
    print("步骤 3：数据验证")
    print("=" * 60)

    with connection.cursor() as cur:
        # 各表行数
        tables = [
            "adminapi_role", "adminapi_adminuser", "adminapi_admintoken",
            "adminapi_tag", "adminapi_questiontag", "adminapi_importjob",
            "adminapi_operationlog", "core_document",
        ]
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t:30s} {cur.fetchone()[0]:5d} 行")

        # core_document 各 collection 行数
        print()
        cur.execute("""
            SELECT collection, COUNT(*) FROM core_document
            GROUP BY collection ORDER BY collection
        """)
        for coll, cnt in cur.fetchall():
            print(f"  core_document[{coll:20s}] {cnt:5d} 行")

        # 外键完整性检查
        print()
        cur.execute("""
            SELECT COUNT(*) FROM adminapi_questiontag qt
            WHERE NOT EXISTS (SELECT 1 FROM core_document WHERE id = qt.question_id)
               OR NOT EXISTS (SELECT 1 FROM adminapi_tag WHERE id = qt.tag_id)
        """)
        orphan_qt = cur.fetchone()[0]
        print(f"  孤立 questiontag 记录: {orphan_qt} (应为 0)")

        cur.execute("""
            SELECT COUNT(*) FROM adminapi_adminuser au
            WHERE au.role_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM adminapi_role WHERE id = au.role_id)
        """)
        orphan_user = cur.fetchone()[0]
        print(f"  孤立 adminuser 记录: {orphan_user} (应为 0)")

        # 唯一约束检查
        cur.execute("""
            SELECT collection, doc_id, COUNT(*) FROM core_document
            GROUP BY collection, doc_id HAVING COUNT(*) > 1
        """)
        dup_docs = cur.fetchall()
        print(f"  重复 (collection, doc_id) 记录: {len(dup_docs)} (应为 0)")

        cur.execute("""
            SELECT name, category, COUNT(*) FROM adminapi_tag
            GROUP BY name, category HAVING COUNT(*) > 1
        """)
        dup_tags = cur.fetchall()
        print(f"  重复 (name, category) 标签: {len(dup_tags)} (应为 0)")


# ============================================================
#  主流程
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("  考试宝数据库清理与示例数据生成")
    print("=" * 60 + "\n")

    # Step 1: 清除
    clear_all_data()

    # Step 2: 生成
    print("=" * 60)
    print("步骤 2：生成示例数据（按外键依赖正序）")
    print("=" * 60)

    roles = seed_roles()
    admin_users = seed_admin_users(roles)
    tags = seed_tags()
    question_docs = seed_core_data()
    seed_question_tags(question_docs, tags)
    seed_import_jobs(admin_users)
    seed_operation_logs(admin_users)
    seed_admin_tokens(admin_users)

    print("\n" + "-" * 40)
    print("示例数据生成完成！")
    print("-" * 40 + "\n")

    # Step 3: 验证
    verify_data()

    print("\n" + "=" * 60)
    print("  全部操作完成！")
    print("=" * 60)
    print(f"\n  管理员账号：")
    print(f"    admin / admin123     （超级管理员）")
    print(f"    operator01 / operator123 （运营人员）")
    print(f"    viewer01 / viewer123  （只读访客）")
    print(f"    operator02 / operator123 （已停用）")
    print()


if __name__ == '__main__':
    main()
