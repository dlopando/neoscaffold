"""Generate the 40-creative Ad Studio example workflow.

Run from ``server/``::

    python -m custom_extensions.ad_studio.build_workflow
"""

import json
import os

from .paths import example_workflow_path
from .prompts import SAMPLE_BRIEF, compose_prompt
from .styles import load_styles

BODY = "#1B1E27"
FAVORITE_INDEX = 3
DISCARD_INDEX = 11
GRID_X = 680
GRID_Y = 36
NODE_W = 320
NODE_H = 530
GAP_X = 36
GAP_Y = 28
COLUMNS = 8


def _slot(name, slot_type, link=None, label=None):
    slot = {"name": name, "type": slot_type, "link": link}
    if label is not None:
        slot["label"] = label
    return slot


def _output(name, slot_type, links):
    return {
        "name": name,
        "type": slot_type,
        "links": links,
        "slot_index": 0,
    }


def _base_node(
    node_id,
    node_type,
    title,
    pos,
    size,
    color,
    widgets,
    inputs,
    outputs,
    properties,
    mode=0,
    order=0,
):
    return {
        "id": node_id,
        "type": node_type,
        "title": title,
        "pos": [pos[0], pos[1]],
        "size": [size[0], size[1]],
        "flags": {},
        "order": order,
        "mode": mode,
        "inputs": inputs,
        "outputs": outputs,
        "properties": properties,
        "widgets_values": widgets,
        "color": color,
        "bgcolor": BODY,
    }


def build_workflow():
    styles = load_styles()
    if len(styles) != 40:
        raise RuntimeError(f"expected 40 styles, found {len(styles)}")

    brand_links = []
    product_links = []
    creative_nodes = []
    links = []

    for index, style in enumerate(styles):
        node_id = 3 + index
        brand_link = index * 2 + 1
        product_link = index * 2 + 2
        brand_links.append(brand_link)
        product_links.append(product_link)
        column = index % COLUMNS
        row = index // COLUMNS
        prompt = compose_prompt(style, SAMPLE_BRIEF, variation="recording preview")
        outputs = []
        creative_nodes.append(
            {
                "node_id": node_id,
                "style": style,
                "brand_link": brand_link,
                "product_link": product_link,
                "column": column,
                "row": row,
                "prompt": prompt,
                "outputs": outputs,
            }
        )
        links.append([brand_link, 1, 0, node_id, 2, "brand_brief"])
        links.append([product_link, 2, 0, node_id, 3, "product_image"])

    frame_link = len(styles) * 2 + 1
    links.append([frame_link, 3, 0, 43, 2, "ad_image"])
    creative_nodes[0]["outputs"] = [frame_link]

    nodes = [
        _base_node(
            1,
            "ad_studio/AdBrandBrief",
            "BRAND WEBSITE + PRODUCT NAME",
            (40, 48),
            (500, 320),
            "#7AA2FF",
            ["https://example.com", "Luma Serum", ""],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
            ],
            [_output("brand_brief", "*", brand_links)],
            {"ad_studio": {"brief": SAMPLE_BRIEF}},
            order=0,
        ),
        _base_node(
            2,
            "ad_studio/AdProductImage",
            "PRODUCT IMAGE",
            (40, 420),
            (500, 460),
            "#FF7AD9",
            ["/ad-studio/placeholders/product.png"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
            ],
            [_output("product_image", "*", product_links)],
            {
                "ad_studio": {
                    "preview_url": "/ad-studio/placeholders/product.png",
                    "image_url": "/ad-studio/placeholders/product.png",
                }
            },
            order=1,
        ),
    ]

    for index, creative in enumerate(creative_nodes):
        style = creative["style"]
        nodes.append(
            _base_node(
                creative["node_id"],
                "ad_studio/AdCreative",
                style["name"].upper(),
                (
                    GRID_X + creative["column"] * (NODE_W + GAP_X),
                    GRID_Y + creative["row"] * (NODE_H + GAP_Y),
                ),
                (NODE_W, NODE_H),
                style["color"],
                [style["id"], "style", "no", "[]", ""],
                [
                    _slot("in_rules", "rule_group", label=""),
                    _slot("out_rules", "rule_group", label=""),
                    _slot(
                        "brand_brief", "brand_brief", creative["brand_link"], "brand"
                    ),
                    _slot(
                        "product_image",
                        "product_image",
                        creative["product_link"],
                        "product",
                    ),
                ],
                [_output("ad", "ad_image", creative["outputs"] or None)],
                {
                    "ad_studio": {
                        "preview_url": f"/ad-studio/placeholders/{style['id']}.png",
                        "prompt": creative["prompt"],
                        "placeholder": True,
                        "favorite": index == FAVORITE_INDEX,
                        "discarded": index == DISCARD_INDEX,
                        "style_id": style["id"],
                        "style_name": style["name"],
                        "model": "placeholder",
                    }
                },
                mode=2 if index == DISCARD_INDEX else 0,
                order=2 + index,
            )
        )

    nodes.append(
        _base_node(
            43,
            "ad_studio/AdFrame916",
            "TO 9:16",
            (GRID_X + COLUMNS * (NODE_W + GAP_X) + 24, GRID_Y),
            (320, 620),
            "#7DFFB3",
            ["cover"],
            [
                _slot("in_rules", "rule_group", label=""),
                _slot("out_rules", "rule_group", label=""),
                _slot("image", "ad_image", frame_link, "ad"),
            ],
            [_output("vertical", "ad_image", None)],
            {
                "ad_studio": {
                    "preview_url": "/ad-studio/placeholders/story_hook_916.png",
                    "prompt": "Cover-crops the connected still to 1080x1920.",
                    "placeholder": True,
                    "style_id": "frame_916",
                    "style_name": "9:16 conversion",
                    "model": "frame",
                }
            },
            order=42,
        )
    )

    grid_width = COLUMNS * NODE_W + (COLUMNS - 1) * GAP_X
    grid_height = 5 * NODE_H + 4 * GAP_Y
    workflow = {
        "last_node_id": 43,
        "last_link_id": frame_link,
        "nodes": nodes,
        "links": links,
        "groups": [
            {
                "title": "40 AD CREATIVES",
                "bounding": [
                    GRID_X - 28,
                    GRID_Y - 46,
                    grid_width + 56,
                    grid_height + 78,
                ],
                "color": "#6D7CFF",
                "font_size": 28,
            }
        ],
        "config": {},
        "extra": {
            "ad_studio": {
                "description": (
                    "Two inputs fan out to 40 ad styles. "
                    "Placeholder stills are labeled PLACEHOLDER until OPENAI_API_KEY is set. "
                    "One creative is pre-favorited and one is discarded so the recording states are visible."
                )
            }
        },
        "version": 0.4,
    }
    return workflow


def write_workflow(path=None):
    destination = path or example_workflow_path()
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    workflow = build_workflow()
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(workflow, handle, indent=2)
        handle.write("\n")
    return destination


if __name__ == "__main__":
    print(write_workflow())
