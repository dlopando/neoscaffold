<div align="center">
  <!-- Version Badge -->
  <a href='https://github.com/neoscaffold/neoscaffold/releases'>
    <img src='https://img.shields.io/badge/version-1.0.2-black?style=for-the-badge'>
  </a>
  <!-- Chat Badge -->
  <a href='https://discord.gg/fWncYRBY'>
    <img src='https://img.shields.io/badge/chat-discord-magenta?logo=discord&style=for-the-badge'>
  </a>
  <!-- Docs Badge -->
  <a href='https://github.com/neoscaffold/neoscaffold/tree/main/docs'>
    <img src='https://img.shields.io/badge/read-docs-blue?style=for-the-badge'>
  </a>
  <!-- Precommit Badge -->
  <a href='https://github.com/neoscaffold/neoscaffold/blob/main/.pre-commit-config.yaml'>
    <img src='https://img.shields.io/badge/githooks-precommit-green?style=for-the-badge'>
  </a>
</div>

<h1 align="center">
  <img src="pictures/neoscaffold-typeface.webp" alt="NeoScaffold Logo"/>
</h1>

NeoScaffold lets you visually program workflows for AI agents and more.

You can import, edit, and export workflows for:
  - building trustworthy and safe AI use-cases
  - iterating quickly on new ideas
  - describing a workflow in natural language and getting a validated graph
  - driving the editor from other agents over OpenAPI and MCP

See [CHANGELOG.md](CHANGELOG.md), the [engineering harness](harness.md), [MCP + OpenAPI](docs/MCP.md), and the [v1.0.0 roadmap](docs/ROADMAP_1.0.0.md).

![-----------------------------------------------------](pictures/aquadivider.png)

## Table of Contents

<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#backstory"> ➤ Backstory 📖🐉</a></li>
    <li><a href="#installation"> ➤ Installation 💿</a></li>
    <li>
      <a href="#fun-with-neoscaffold"> ➤ Fun With NeoScaffold 🎨</a>
      <ul>
        <li><a href="#natural-language-graphs"> ➤ Natural-Language Graphs 💬</a></li>
        <li><a href="#controlling-neoscaffold-from-other-agents"> ➤ Controlling NeoScaffold from Other Agents 🤖</a></li>
        <li><a href="#building-an-ai-persona-agent"> ➤ Building an AI Persona Agent 🕴️</a></li>
        <li><a href="#custom-extensions-for-more-nodes"> ➤ Custom Extensions for More Nodes 🧩</a></li>
        <li><a href="#ad-studio"> ➤ Ad Studio 📺</a></li>
        <li><a href="#rules-for-reliable-quality"> ➤ Rules for Reliable Quality 🔍</a></li>
      </ul>
    </li>
    <li><a href="#contributing-directly"> ➤ Contributing Directly 🤝</a></li>
    <li><a href="#issues"> ➤ Issues 🐛</a></li>
    <li><a href="#faq"> ➤ FAQ 🤔</a></li>
    <li><a href="#changelog"> ➤ Changelog 📜</a></li>
    <li><a href="#contributors"> ➤ Contributors 🤝</a></li>
    <li><a href="#license"> ➤ License 📄</a></li>
    <li><a href="#views"> ➤ Views 👀</a></li>
  </ol>
</details>

![-----------------------------------------------------](pictures/aquadivider.png)

## Backstory

[ComfyUI](https://github.com/comfyanonymous/ComfyUI) provided us a new way to build ai inference workflows to create images, and animations. Now, we don't need to write code to setup the inference pipelines, instead we visually program using nodes. Sleepless nights are now spent creating amazing art and pipelines to breath life to our work.


NeoScaffold aims to do same to many more workflows.


Emphasizing the following more:
  - Friendly development experience
  - No-compromises support for runtime quality checks on node inputs or node outputs
  - [litegraph.js](https://github.com/jagenjo/litegraph.js) sharing ComfyUI's front-end graph engine

![-----------------------------------------------------](pictures/aquadivider.png)

## Installation

First Git clone this repo.

NeoScaffold requires using at least node 18 and python 3.10.

To setup python 3.10 we recommend [uv](https://docs.astral.sh/uv/concepts/python-versions/#installing-a-python-version) or [pyenv](https://github.com/pyenv/pyenv#readme).


To get the backend up and running use uv:

```bash
# change to server folder
cd server;

# make sure there's a virtual environment
uv venv;

# activate it
source .venv/bin/activate;

# install the dependencies
uv sync;

# run the server
python main.py;

# optionally run the server with delay to watch the output of the nodes
python main.py --inspection-delay 1;

# optionally run prompts with the parallel graph executor by default
python main.py --enable-parallel-execution --max-parallel-nodes 8;
```

To get the front-end server running:

We recommend using a node version manager like [nvm](https://github.com/nvm-sh/nvm) to install node 18 if you don't already have it.

Our example front-end uses [Ember.js CLI](https://cli.emberjs.com/release/) version [5.8](https://blog.emberjs.com/ember-released-5-8/)

```bash
# Change to the frontend directory
cd neoscaffold;

# Use Node.js version 18
nvm use 18;

# to get ember-cli globally
npm i --global ember-cli@5.8

# Install dependencies using clean-install
npm ci;

# Start the front-end server
npm start;
```

![-----------------------------------------------------](pictures/aquadivider.png)

## Fun With NeoScaffold

NeoScaffold can be a colorful and fun way to build workflows. You can use existing nodes, describe a workflow in the Prompt bar, or create your own nodes.

![-----------------------------------------------------](pictures/aquadivider.png)

### Natural-Language Graphs

The Prompt overlay in the editor sends your request to `POST /v1/agent/build-graph`. The harness planner returns a validated prompt-graph (offline and deterministic by default; an LLM planner when `OPENAI_API_KEY` is set). The editor inserts the nodes, wires them, and keeps a conversation of thoughts and outputs. When a run fails, the same conversation can ask how to fix the graph and arm a patch for Accept.

Import and export portable workflow JSON with `POST /v1/agent/import-workflow` and `POST /v1/agent/export-workflow`.

![-----------------------------------------------------](pictures/aquadivider.png)

### Controlling NeoScaffold from Other Agents

v1.0.0 is designed to be driven by other agents. `GET /v1/openapi.json` is the HTTP contract. MCP tools are derived from that spec (`GET /v1/mcp/tools`); run `server/mcp_server.py` against a live server. See [docs/MCP.md](docs/MCP.md).

Health and metrics: `GET /v1/healthz`, `GET /v1/metrics` (Prometheus). Live subagent spans and per-node streams: `GET /v1/agent/events` and the Agent Activity panel.

![-----------------------------------------------------](pictures/aquadivider.png)

### Building an AI Persona Agent

#### TODO: Add a gif of the persona agent
#### TODO: add a step by step guide to building the persona agent

![-----------------------------------------------------](pictures/aquadivider.png)

### Custom Extensions for More Nodes

NeoScaffold provides a way to create extensions that give developers a way to add new nodes to the graph. Their core functionality is defined in python, however the user can provide a non-default litegraph.js "node" to customize the node's appearance in the graph.

Extensions are defined in python with a simple dict-interface like this included in a ```extension.py``` file:

```python
# in server/custom_extensions/image_utilities/extension.py

# Example Node
class PreviewImageURL:
    # LABELS
    CATEGORY = "images"
    SUBCATEGORY = "image"
    DESCRIPTION = "preview image url"

    # INPUT TYPES
    INPUT = {
        "required_inputs": {
            "url": {
                "kind": "*",
                "name": "url",
                "widget": {"kind": "string", "name": "url", "default": ""},
            },
        }
    }

    # OUTPUT TYPES
    OUTPUT = {
        "kind": "RESPONSE",
        "name": "RESPONSE",
        "cacheable": True,
    }

    # METHODS
    def evaluate(self, node_inputs):
        self.url = node_inputs.get("required_inputs").get("url").get("values")
        return self.url

# Example Extension
EXTENSION_MAPPINGS = {
    "name": "ImageUtilities",
    "version": version,
    "description": "Extension for additional image nodes",
    "javascript_class_name": "ImageUtilities",
    "nodes": {
        "PreviewImageURL": {
            "python_class": PreviewImageURL,
            "javascript_class_name": "PreviewImageURL",
            "display_name": "PreviewImageURL",
        },
    },
    "rules": {},
}

```


![-----------------------------------------------------](pictures/aquadivider.png)

### Ad Studio

Ad Studio turns a brand website and a product photo into a grid of static ad creatives. The example workflow fans two input nodes out to 40 styles (claymation, iMessage, a fake X post, headline posters, and several 9:16 story frames) plus a node that cover-crops one still to 1080×1920.

Set `OPENAI_API_KEY` before starting the server. Image generation uses `gpt-image-2` (`images.edit`, so the uploaded product photo is the reference). Brand extraction uses `gpt-4.1-mini` unless `AD_STUDIO_TEXT_MODEL` is set. Override the image model with `AD_STUDIO_IMAGE_MODEL`.

Without a key, the same graph still runs: prompts are composed from the style library and the nodes save clearly labeled placeholder PNGs. That path is what the unit tests and the preview canvas use.

```bash
cd server
uv sync
source .venv/bin/activate
export OPENAI_API_KEY=sk-...
python main.py --enable-parallel-execution --max-parallel-nodes 6 --output-directory ./output
```

Generated stills land in `output/ad_studio/` and are served at `/ad-studio/outputs/<file>.png`. Uploads go to `input/ad_studio/` (`--input-directory` or `NEOSCAFFOLD_INPUT_DIRECTORY`).

In another terminal, start the editor and open the example graph:

```bash
cd neoscaffold
npm ci
npm start
```

Open `http://localhost:4200/workflow?workflow=http://127.0.0.1:6166/ad-studio/workflows/ad_studio_40.json`.

Switch the toolbar from `SEQ` to `PAR` if the server was not started with `--enable-parallel-execution`, then queue the prompt. Each creative shows the prompt and the still. **Keep** leaves it in the next run, **Discard** mutes the node (mode Never) so it is skipped and the image stays, greyed out, and **Favorite** stores the prompt and image so the next run riffs on those ads. Favorites are collected in the browser when you queue; discarded nodes are not sent.

A quick canvas without the Ember shell is at `http://127.0.0.1:6166/ad-studio/preview`. Placeholder images there are not model output.

Edit styles in `server/custom_extensions/ad_studio/catalog.py`, then regenerate the example graph:

```bash
cd server
python -m custom_extensions.ad_studio.build_workflow
```

The creative result (`prompt`, `image_path`, `width`, `height`, `aspect`) is shaped so a later step can assemble screen recordings. That video pass is not part of this feature.

![-----------------------------------------------------](pictures/aquadivider.png)

### Rules for Reliable Quality

#### TODO: Add a gif of the rules in action
#### TODO: add a step by step guide to building the rules

![-----------------------------------------------------](pictures/aquadivider.png)

## Contributing Directly

See [CONTRIBUTING.md](https://github.com/neoscaffold/neoscaffold/blob/main/CONTRIBUTING.md)

![-----------------------------------------------------](pictures/aquadivider.png)

## Issues

We ask our users to create issues if they see a bug, or would like to request a feature from the team.

If you have a question or concern please feel free to reach out on the respective team's channel and we will help you usually within the business day.

![-----------------------------------------------------](pictures/aquadivider.png)

## FAQ

See [FAQ.md](https://github.com/neoscaffold/neoscaffold/blob/main/FAQ.md)

![-----------------------------------------------------](pictures/aquadivider.png)

## Changelog

See [CHANGELOG.md](https://github.com/neoscaffold/neoscaffold/blob/main/CHANGELOG.md)

![-----------------------------------------------------](pictures/aquadivider.png)

## Author

Conrad Lippert-Zajaczkowski

![-----------------------------------------------------](pictures/aquadivider.png)

## License

This project is Apache 2.0 licensed.

![-----------------------------------------------------](pictures/aquadivider.png)

## Views

![Visitor Count](https://profile-counter.glitch.me/neoscaffold/count.svg)
