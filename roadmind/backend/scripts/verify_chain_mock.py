"""D6 闭环核心逻辑验证（纯逻辑版，不依赖 app/依赖，任何环境可跑）。

直接验证责任判定 + 应急方案的规则逻辑，模拟 M3(M4) 智能体输出。
"""
from collections import Counter

# ---- 模拟：RAG 检索到的法条 ----
_LAW_POOL = [
    {"id": "law-043", "title": "道交法 第43条", "source": "law",
     "content": "同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。"},
    {"id": "law-044", "title": "实施条例 第44条", "source": "law",
     "content": "变更车道的机动车不得影响相关车道内行驶的机动车的正常行驶。"},
    {"id": "law-047", "title": "道交法 第47条", "source": "law",
     "content": "机动车通过没有信号灯的路口应当减速慢行，让行人和优先通行的车辆先行。"},
    {"id": "law-051", "title": "实施条例 第51条", "source": "law",
     "content": "转弯的机动车让直行的车辆先行。"},
]


def simple_retrieve(query, top_k=4):
    scored = []
    for doc in _LAW_POOL:
        score = sum(1 for t in ("追尾", "变道", "路口", "让行", "灯") if t in query and t in doc["content"])
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for s, d in scored[:top_k] if s > 0]


# ---- 模拟：M3 责任判定 ----
def judge(text, retrieved):
    if "追尾" in text:
        return {
            "responsibility": {"party_1": "primary", "party_2": "none", "split": "100/0"},
            "basis": ["道交法 第43条"],
            "reasoning": ["后车未与前车保持安全距离", "前车正常行驶无过错"],
            "confidence": 0.8,
        }
    if "转弯" in text or "让行" in text:
        return {
            "responsibility": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
            "basis": ["实施条例 第51条", "道交法 第47条"],
            "reasoning": ["转弯车未让行直行车", "直行车未尽注意义务"],
            "confidence": 0.75,
        }
    return {
        "responsibility": {"party_1": "unknown", "party_2": "unknown", "split": ""},
        "basis": [], "reasoning": ["要素不足"], "confidence": 0.3,
    }


# ---- 模拟：M4 应急方案 ----
_TEMPLATES = {
    "vehicle_pedestrian": {
        "priority": 1,
        "steps": [
            {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
            {"order": 2, "action": "拨打 120 急救", "urgent": True},
            {"order": 3, "action": "拨打 122/110 报警", "urgent": True},
            {"order": 4, "action": "放置三角警示牌", "urgent": True},
            {"order": 5, "action": "保护现场，勿移动伤员", "urgent": True},
        ],
        "insurance": "同步报保险，拍摄现场照片与全景视频。",
    },
    "rear_end": {
        "priority": 2,
        "steps": [
            {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
            {"order": 2, "action": "放置三角警示牌", "urgent": True},
            {"order": 3, "action": "人员撤至安全地带", "urgent": True},
        ],
        "insurance": "报保险，保留现场照片与行车记录仪。",
    },
}


def draft_response(accident_type):
    return _TEMPLATES.get(accident_type, {"priority": 2,
                                          "steps": [{"order": 1, "action": "开启双闪，停车", "urgent": True}],
                                          "insurance": "保留证据并报保险"})


def run_case(text):
    print("=" * 50)
    print(f"输入: {text}")
    retrieved = simple_retrieve(text)
    print(f"RAG 检索: {len(retrieved)} 条 -> {[d['title'] for d in retrieved]}")
    j = judge(text, retrieved)
    print(f"责任判定: {j['responsibility']}  置信度 {j['confidence']}")
    print(f"  依据: {j['basis']}")
    print(f"  理由: {j['reasoning']}")
    accident_type = "vehicle_pedestrian" if ("行人" in text or "撞人" in text
                                             or "下车" in text and "被撞" in text) \
        else ("rear_end" if "追尾" in text else "general")
    r = draft_response(accident_type)
    print(f"应急方案({accident_type}, 优先级{r['priority']}):")
    for s in r["steps"]:
        print(f"  {s['order']}. {s['action']}{' [紧急]' if s['urgent'] else ''}")
    print(f"  保险: {r['insurance']}")


if __name__ == "__main__":
    print("D6 闭环逻辑验证（纯逻辑，无需依赖）\n")
    run_case("路口我车直行，对方左转弯未让行，两车碰撞")
    run_case("后车追尾前车，前车正常行驶，前车司机下车后被撞")
