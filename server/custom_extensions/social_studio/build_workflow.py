"""Generate the Social Studio dry-run example workflow.

Run from ``server/``::

    python -m custom_extensions.social_studio.build_workflow
"""

import json
import os

from custom_extensions.ad_studio.prompts import SAMPLE_BRIEF, compose_prompt
from custom_extensions.ad_studio.styles import get_style

BODY = "#1B1E27"


def _slot(name, slot_type, link=None, label=None):
    slot = {"name": name, "type": slot_type, "link": link}
    if label is not None:
        slot["label"] = label
    return slot


def _output(name, slot_type, links):
    return {"name": name, "type": slot_type, "links": links, "slot_index": 0}


def _node(node_id, node_type, title, pos, size, color, widgets, inputs, outputs, properties, mode=0):
    return {
        "id": node_id,
        "type": node_type,
        "title": title,
        "pos": [pos[0], pos[1]],
        "size": [size[0], size[1]],
        "flags": {},
        "order": node_id,
        "mode": mode,
        "inputs": inputs,
        "outputs": outputs,
        "properties": properties,
        "widgets_values": widgets,
        "color": color,
        "bgcolor": BODY,
    }


def _creative(node_id, style_id, pos, brand_link, product_link, favorite=False, discarded=False):
    style = get_style(style_id)
    prompt = compose_prompt(style, SAMPLE_BRIEF, variation="social studio dry run")
    return _node(
        node_id,
        "ad_studio/AdCreative",
        style["name"].upper(),
        pos,
        (320, 530),
        style.get("color") or "#8AB4FF",
        [style_id, "style", "no", "[]", ""],
        [
            _slot("in_rules", "rule_group", label=""),
            _slot("out_rules", "rule_group", label=""),
            _slot("brand_brief", "brand_brief", brand_link, "brand"),
            _slot("product_image", "product_image", product_link, "product"),
        ],
        [_output("ad", "ad_image", [])],
        {
            "ad_studio": {
                "preview_url": f"/ad-studio/placeholders/{style_id}.png",
                "prompt": prompt,
                "placeholder": True,
                "favorite": favorite,
                "discarded": discarded,
                "style_id": style_id,
                "style_name": style["name"],
                "model": "placeholder",
            }
        },
        mode=2 if discarded else 0,
    )


def build_workflow():
    selection = [
        {"index": 0, "favorite": True, "discarded": False},
        {"index": 1, "favorite": False, "discarded": False},
        {"index": 2, "favorite": True, "discarded": False},
        {"index": 3, "favorite": False, "discarded": True},
    ]
    nodes = [
        _node(
            1,
            "ad_studio/AdBrandBrief",
            "BRAND WEBSITE + PRODUCT NAME",
            (40, 40),
            (480, 280),
            "#7AA2FF",
            ["https://example.com", "Luma Serum", ""],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
            ],
            [_output("brand_brief", "*", [1, 3, 5])],
            {"ad_studio": {"brief": SAMPLE_BRIEF}},
        ),
        _node(
            2,
            "ad_studio/AdProductImage",
            "PRODUCT IMAGE",
            (40, 360),
            (480, 300),
            "#FF7AD9",
            ["/ad-studio/placeholders/product.png"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
            ],
            [_output("product_image", "product_image", [2, 4, 6])],
            {
                "ad_studio": {
                    "preview_url": "/ad-studio/placeholders/product.png",
                    "image_url": "/ad-studio/placeholders/product.png",
                }
            },
        ),
        _creative(3, "claymation", (620, 40), 1, 2, favorite=True),
        _creative(4, "dont_buy_this", (980, 40), 3, 4),
        _creative(5, "fake_tweet", (1340, 40), 5, 6, discarded=True),
        _node(
            6,
            "ad_studio/AdFrame916",
            "TO 9:16",
            (620, 620),
            (320, 560),
            "#7DFFB3",
            ["cover"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
                _slot("image", "ad_image", 7, "ad"),
            ],
            [_output("vertical", "ad_image", [10])],
            {"ad_studio": {"placeholder": True, "favorite": True, "style_name": "9:16 conversion"}},
        ),
        _node(
            7,
            "social_studio/SocialAccountSelect",
            "ACCOUNT SELECT",
            (40, 720),
            (340, 280),
            "#F0C36A",
            ["tag", "luma", ""],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
            ],
            [_output("accounts", "account_set", [12])],
            {},
        ),
        _node(
            8,
            "social_studio/SocialCaptionVariations",
            "CAPTION VARIATIONS",
            (1760, 80),
            (360, 420),
            "#C9A6FF",
            ["3", "", "", "auto", "all_kept", json.dumps(selection)],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
                _slot("creative", "ad_image", 8),
                _slot("creative_2", "ad_image", 9),
                _slot("creative_3", "ad_image", 10),
                _slot("creative_4", "ad_image", 11),
                _slot("brand_brief", "brand_brief", 13),
            ],
            [_output("pack", "caption_pack", [14])],
            {"social_studio": {}},
        ),
        _node(
            9,
            "social_studio/SocialDistribute",
            "DISTRIBUTE / POST",
            (2200, 80),
            (420, 480),
            "#7DFFB3",
            ["round-robin", "yes", "", "90", "15", "all_kept", "platform_default", "[]"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
                _slot("creatives", "caption_pack", 14, "creatives"),
                _slot("accounts", "account_set", 12, "accounts"),
                _slot("captions", "*", None),
            ],
            [_output("plan", "post_plan", [15])],
            {"social_studio": {"dry_run": True}},
        ),
        _node(
            10,
            "social_studio/SocialPostLog",
            "POST LOG",
            (2700, 80),
            (420, 320),
            "#8EB4FF",
            ["20"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
                _slot("plan", "post_plan", 15),
            ],
            [_output("log", "post_log", None)],
            {},
        ),
    ]
    nodes[2]["outputs"][0]["links"] = [7, 8]
    nodes[3]["outputs"][0]["links"] = [9]
    nodes[4]["outputs"][0]["links"] = [11]
    links = [
        [1, 1, 0, 3, 2, "brand_brief"],
        [2, 2, 0, 3, 3, "product_image"],
        [3, 1, 0, 4, 2, "brand_brief"],
        [4, 2, 0, 4, 3, "product_image"],
        [5, 1, 0, 5, 2, "brand_brief"],
        [6, 2, 0, 5, 3, "product_image"],
        [7, 3, 0, 6, 2, "ad_image"],
        [8, 3, 0, 8, 2, "ad_image"],
        [9, 4, 0, 8, 3, "ad_image"],
        [10, 6, 0, 8, 4, "ad_image"],
        [11, 5, 0, 8, 5, "ad_image"],
        [12, 7, 0, 9, 3, "account_set"],
        [13, 1, 0, 8, 6, "brand_brief"],
        [14, 8, 0, 9, 2, "caption_pack"],
        [15, 9, 0, 10, 2, "post_plan"],
    ]
    # Brand output also feeds the caption node. The brand node's link list
    # above only named the three creatives; add the caption link.
    nodes[0]["outputs"][0]["links"] = [1, 3, 5, 13]
    return {
        "last_node_id": 10,
        "last_link_id": 15,
        "nodes": nodes,
        "links": links,
        "groups": [
            {
                "title": "AD STUDIO OUTPUT",
                "bounding": [590, 10, 1100, 1200],
                "color": "#6D7CFF",
                "font_size": 24,
            },
            {
                "title": "SOCIAL STUDIO  DRY RUN",
                "bounding": [1720, 20, 1460, 620],
                "color": "#3DDC97",
                "font_size": 24,
            },
        ],
        "config": {},
        "extra": {
            "social_studio": {
                "description": "Kept and favorited Ad Studio creatives go to caption variations, then DISTRIBUTE / POST with dry run on. The discarded creative is wired and skipped. Accounts come from the luma tag."
            }
        },
        "version": 0.4,
    }


def main():
    from .paths import example_workflow_path

    payload = build_workflow()
    destination = example_workflow_path()
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(destination)


if __name__ == "__main__":
    main()
