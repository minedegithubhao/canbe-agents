from __future__ import annotations

from app.evaluation.text_repair import repair_text


def test_repair_text_decodes_latin1_mojibake():
    mojibake = "配送方式".encode("utf-8").decode("latin1")

    assert repair_text(mojibake) == "配送方式"


def test_repair_text_decodes_question_with_c1_controls():
    mojibake = "为何物流显示签收，却没有收到？".encode("utf-8").decode("latin1")

    assert repair_text(mojibake) == "为何物流显示签收，却没有收到？"


def test_repair_text_keeps_normal_chinese():
    assert repair_text("订单相关") == "订单相关"
