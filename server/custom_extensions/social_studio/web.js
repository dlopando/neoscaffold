// Social Studio node UI. Loaded by NeoScaffold and by GET /social-studio/client.js.
(function (root) {
  var BODY = "#1B1E27";

  root.NeoScaffoldExtras = root.NeoScaffoldExtras || { ext: {}, nodes: {}, rules: {} };
  root.NeoScaffoldExtras.nodes = root.NeoScaffoldExtras.nodes || {};

  if (typeof LGraphCanvas !== "undefined" && LGraphCanvas.link_type_colors) {
    LGraphCanvas.link_type_colors.account_set = "#F0C36A";
    LGraphCanvas.link_type_colors.caption_pack = "#C9A6FF";
    LGraphCanvas.link_type_colors.post_plan = "#7DFFB3";
    LGraphCanvas.link_type_colors.post_log = "#8EB4FF";
  }

  function apiBase() {
    if (root.NeoScaffold && root.NeoScaffold.api && root.NeoScaffold.api.baseURL) {
      return String(root.NeoScaffold.api.baseURL).replace(/\/$/, "");
    }
    if (root.NEOSCAFFOLD_API_BASE) {
      return String(root.NEOSCAFFOLD_API_BASE).replace(/\/$/, "");
    }
    return "";
  }

  function findWidget(node, name) {
    var widgets = node.widgets || [];
    for (var i = 0; i < widgets.length; i++) {
      if (widgets[i] && widgets[i].name === name) return widgets[i];
    }
    return null;
  }

  function widgetValue(node, name, fallback) {
    var widget = findWidget(node, name);
    if (!widget || widget.value == null || widget.value === "") return fallback;
    return widget.value;
  }

  function resultValues(node) {
    var result = node.properties && node.properties.result && node.properties.result.result;
    if (result && result.values && typeof result.values === "object") return result.values;
    return null;
  }

  function ensureStudio(node) {
    node.properties = node.properties || {};
    if (!node.properties.social_studio || typeof node.properties.social_studio !== "object") {
      node.properties.social_studio = {};
    }
    return node.properties.social_studio;
  }

  function hideWidget(widget) {
    widget.type = "social_hidden";
    widget.computeSize = function () { return [0, -4]; };
    widget.draw = function () {};
    widget.disabled = true;
  }

  function addRuleInputs(node) {
    var rulesIn = node.addInput("in_rules", "rule_group");
    var rulesOut = node.addInput("out_rules", "rule_group");
    rulesIn.label = "";
    rulesOut.label = "";
  }

  function contentTop(node) {
    var top = 6;
    var widgets = node.widgets || [];
    for (var i = 0; i < widgets.length; i++) {
      var widget = widgets[i];
      if (!widget || widget.type === "social_hidden" || widget.name === "selection_json") continue;
      if (widget.last_y == null) continue;
      var height = widget.computeSize ? widget.computeSize(node.size[0])[1] : 20;
      if (height < 1) continue;
      top = Math.max(top, widget.last_y + height + 8);
    }
    return top;
  }

  function roundRect(ctx, x, y, w, h, radius) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, radius);
    else ctx.rect(x, y, w, h);
  }

  function remember(node) {
    var values = resultValues(node);
    if (!values) return;
    ensureStudio(node).last = values;
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
  }

  function collectSelection(node) {
    var selection = [];
    var index = 0;
    var inputs = node.inputs || [];
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      if (!input || input.link == null || !node.graph || !node.graph.links) continue;
      if (input.name === "in_rules" || input.name === "out_rules" || input.name === "accounts" || input.name === "brand_brief" || input.name === "captions" || input.name === "plan") {
        continue;
      }
      var link = node.graph.links[input.link];
      if (!link) continue;
      var origin = node.graph.getNodeById(link.origin_id);
      if (!origin) continue;
      if (origin.type !== "ad_studio/AdCreative" && origin.type !== "ad_studio/AdFrame916") continue;
      var studio = (origin.properties && origin.properties.ad_studio) || {};
      selection.push({
        index: index,
        image_path: studio.image_path || "",
        favorite: !!studio.favorite,
        discarded: origin.mode === 2 || !!studio.discarded
      });
      index += 1;
    }
    var widget = findWidget(node, "selection_json");
    if (widget && selection.length) widget.value = JSON.stringify(selection);
  }

  function AccountSelectNode() {
    this.serialize_widgets = true;
    this.color = "#F0C36A";
    this.bgcolor = BODY;
    this.title = "ACCOUNT SELECT";
    addRuleInputs(this);
    this.addOutput("accounts", "account_set");
    this.addWidget("combo", "mode", "tag", function () {}, { values: ["tag", "ids"] });
    this.addWidget("string", "tag", "luma", function () {}, {});
    this.addWidget("string", "account_ids", "", function () {}, {});
    this.hooks = { didExecute: [remember] };
    this.size = AccountSelectNode.size.concat();
  }
  AccountSelectNode.title = "ACCOUNT SELECT";
  AccountSelectNode.desc = "Connected accounts by tag or id. Tokens are not on this wire.";
  AccountSelectNode.size = [340, 280];
  AccountSelectNode.prototype.onDrawForeground = function (ctx) {
    var values = resultValues(this) || (ensureStudio(this).last || {});
    var accounts = values.accounts || [];
    var top = contentTop(this);
    ctx.save();
    ctx.font = "13px sans-serif";
    ctx.fillStyle = "#E6E8EE";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    if (!accounts.length) {
      ctx.fillText("No accounts on this wire yet.", 14, top);
      ctx.fillStyle = "#8E95A8";
      ctx.fillText("Connect them at /social-studio/accounts", 14, top + 20);
      ctx.restore();
      return;
    }
    accounts.slice(0, 6).forEach(function (account, index) {
      var label = (account.platform || "") + "  " + (account.handle || "");
      ctx.fillText(label, 14, top + index * 18);
    });
    ctx.restore();
  };

  function CaptionNode() {
    var node = this;
    this.serialize_widgets = true;
    this.color = "#C9A6FF";
    this.bgcolor = BODY;
    this.title = "CAPTION VARIATIONS";
    addRuleInputs(this);
    this.addInput("creative", "ad_image");
    this.addInput("creative_2", "ad_image");
    this.addInput("creative_3", "ad_image");
    this.addInput("creative_4", "ad_image");
    this.addInput("brand_brief", "brand_brief");
    this.addOutput("pack", "caption_pack");
    this.addWidget("string", "count", "3", function () {}, {});
    this.addWidget("string", "tone", "", function () {}, {});
    this.addWidget("string", "instructions", "", function () {}, {});
    this.addWidget("combo", "use_model", "auto", function () {}, { values: ["auto", "yes", "no"] });
    this.addWidget("combo", "include", "all_kept", function () {}, { values: ["all_kept", "favorites_only"] });
    hideWidget(this.addWidget("string", "selection_json", "[]", function () {}, {}));
    this.hooks = {
      willQueue: [function () { collectSelection(node); }],
      didExecute: [remember]
    };
    this.size = CaptionNode.size.concat();
  }
  CaptionNode.title = "CAPTION VARIATIONS";
  CaptionNode.desc = "N caption and hashtag variants per kept creative.";
  CaptionNode.size = [360, 360];
  CaptionNode.prototype.onDrawForeground = function (ctx) {
    var values = resultValues(this) || {};
    var top = contentTop(this);
    ctx.save();
    ctx.font = "13px sans-serif";
    ctx.fillStyle = "#E6E8EE";
    ctx.textBaseline = "top";
    var model = values.model ? "Model  " + values.model : "Heuristic until a run, or the text model when a key is set.";
    ctx.fillText(model, 14, top);
    var captions = values.captions || [];
    if (captions.length && captions[0].variants && captions[0].variants.length) {
      ctx.fillStyle = "#C9D0DE";
      ctx.fillText(String(captions[0].variants[0]).slice(0, 80), 14, top + 22);
    }
    ctx.restore();
  };

  function DistributeNode() {
    var node = this;
    this.serialize_widgets = true;
    this.color = "#7DFFB3";
    this.bgcolor = BODY;
    this.title = "DISTRIBUTE / POST";
    addRuleInputs(this);
    var creatives = this.addInput("creatives", "caption_pack");
    creatives.label = "creatives";
    var accounts = this.addInput("accounts", "account_set");
    accounts.label = "accounts";
    this.addInput("captions", "*");
    this.addOutput("plan", "post_plan");
    this.addWidget("combo", "strategy", "round-robin", function () {}, { values: ["round-robin", "random", "all-to-all"] });
    this.addWidget("combo", "dry_run", "yes", function () {}, { values: ["yes", "no"] });
    this.addWidget("string", "schedule_at", "", function () {}, {});
    this.addWidget("string", "stagger_seconds", "0", function () {}, {});
    this.addWidget("string", "jitter_seconds", "0", function () {}, {});
    this.addWidget("combo", "include", "all_kept", function () {}, { values: ["all_kept", "favorites_only"] });
    this.addWidget("combo", "privacy", "platform_default", function () {}, { values: ["platform_default", "public", "private"] });
    hideWidget(this.addWidget("string", "selection_json", "[]", function () {}, {}));
    this.hooks = {
      willQueue: [function () { collectSelection(node); }],
      didExecute: [remember]
    };
    this.size = DistributeNode.size.concat();
  }
  DistributeNode.title = "DISTRIBUTE / POST";
  DistributeNode.desc = "Assign variations across accounts. Dry run is the default.";
  DistributeNode.size = [420, 460];
  DistributeNode.prototype.onDrawForeground = function (ctx) {
    var values = resultValues(this) || {};
    var top = contentTop(this);
    var dry = widgetValue(this, "dry_run", "yes") !== "no";
    if (values.dry_run != null) dry = !!values.dry_run;
    ctx.save();
    ctx.font = "bold 12px sans-serif";
    ctx.fillStyle = dry ? "#3A2A12" : "#143024";
    roundRect(ctx, 12, top, dry ? 148 : 120, 22, 8);
    ctx.fill();
    ctx.fillStyle = dry ? "#FFD27A" : "#B8FFD8";
    ctx.textBaseline = "middle";
    ctx.fillText(dry ? "DRY RUN  DEFAULT" : "LIVE QUEUE", 20, top + 11);
    ctx.restore();
    var items = values.items || [];
    ctx.save();
    ctx.font = "12px sans-serif";
    ctx.fillStyle = "#E6E8EE";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    if (!items.length) {
      ctx.fillStyle = "#8E95A8";
      ctx.fillText("Plan preview appears here after a run.", 14, top + 32);
      ctx.restore();
      return;
    }
    items.slice(0, 5).forEach(function (item, index) {
      var creative = item.creative || {};
      var line = (item.platform || "") + "  " + (item.handle || "") + "  " + (creative.style_name || "") + "  " + (item.status || "");
      ctx.fillText(line.slice(0, 64), 14, top + 32 + index * 16);
    });
    ctx.restore();
  };

  function PostLogNode() {
    this.serialize_widgets = true;
    this.color = "#8EB4FF";
    this.bgcolor = BODY;
    this.title = "POST LOG";
    addRuleInputs(this);
    this.addInput("plan", "post_plan");
    this.addOutput("log", "post_log");
    this.addWidget("string", "limit", "20", function () {}, {});
    this.hooks = { didExecute: [remember] };
    this.size = PostLogNode.size.concat();
  }
  PostLogNode.title = "POST LOG";
  PostLogNode.desc = "Account, creative, caption, time, permalink or error.";
  PostLogNode.size = [420, 320];
  PostLogNode.prototype.onDrawForeground = function (ctx) {
    var values = resultValues(this) || {};
    var posts = values.posts || [];
    var top = contentTop(this);
    ctx.save();
    ctx.font = "12px sans-serif";
    ctx.fillStyle = "#E6E8EE";
    ctx.textBaseline = "top";
    if (!posts.length) {
      ctx.fillStyle = "#8E95A8";
      ctx.fillText("Log is empty. Open /social-studio/log", 14, top);
      ctx.restore();
      return;
    }
    posts.slice(0, 6).forEach(function (post, index) {
      var line = (post.status || "") + "  " + (post.platform || "") + "  " + (post.handle || "");
      ctx.fillText(line.slice(0, 62), 14, top + index * 16);
    });
    ctx.restore();
  };

  function mountLauncher() {
    var doc = root.document;
    if (!doc || !doc.body || doc.getElementById("social-studio-launcher")) return;
    var link = doc.createElement("a");
    link.id = "social-studio-launcher";
    link.href = apiBase() + "/social-studio/accounts";
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Social accounts";
    link.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:40;background:#35548f;color:#f4f6fb;text-decoration:none;border-radius:999px;padding:8px 12px;font:13px/1.2 system-ui,sans-serif;";
    doc.body.appendChild(link);
  }

  root.NeoScaffoldExtras.nodes["social_studio/SocialAccountSelect"] = AccountSelectNode;
  root.NeoScaffoldExtras.nodes["social_studio/SocialCaptionVariations"] = CaptionNode;
  root.NeoScaffoldExtras.nodes["social_studio/SocialDistribute"] = DistributeNode;
  root.NeoScaffoldExtras.nodes["social_studio/SocialPostLog"] = PostLogNode;

  if (typeof LiteGraph !== "undefined" && LiteGraph.registerNodeType) {
    LiteGraph.registerNodeType("social_studio/SocialAccountSelect", AccountSelectNode);
    LiteGraph.registerNodeType("social_studio/SocialCaptionVariations", CaptionNode);
    LiteGraph.registerNodeType("social_studio/SocialDistribute", DistributeNode);
    LiteGraph.registerNodeType("social_studio/SocialPostLog", PostLogNode);
  }

  if (root.document && root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", mountLauncher);
  } else {
    mountLauncher();
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
