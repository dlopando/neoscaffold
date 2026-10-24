// Ad Studio node UI. Evaluated by NeoScaffold.loadExtensions and by
// GET /ad-studio/client.js. Keep / Discard / Favorite are drawn on the
// creative so a screen recording can read the state without opening a panel.
(function (root) {
  var STYLES = []/*__AD_STUDIO_STYLES__*/;
  var BODY = "#1B1E27";
  var STYLE_BY_ID = {};
  var STYLE_IDS = [];
  for (var styleIndex = 0; styleIndex < STYLES.length; styleIndex++) {
    STYLE_BY_ID[STYLES[styleIndex].id] = STYLES[styleIndex];
    STYLE_IDS.push(STYLES[styleIndex].id);
  }
  if (!STYLE_IDS.length) {
    STYLE_IDS = ["claymation"];
  }

  root.NeoScaffoldExtras = root.NeoScaffoldExtras || { ext: {}, nodes: {}, rules: {} };
  root.NeoScaffoldExtras.nodes = root.NeoScaffoldExtras.nodes || {};

  if (typeof LGraphCanvas !== "undefined" && LGraphCanvas.link_type_colors) {
    LGraphCanvas.link_type_colors.brand_brief = "#7AA2FF";
    LGraphCanvas.link_type_colors.product_image = "#FF7AD9";
    LGraphCanvas.link_type_colors.ad_image = "#7DFFB3";
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

  function resolveUrl(url) {
    if (!url) return "";
    var text = String(url);
    if (/^https?:\/\//i.test(text) || text.indexOf("data:") === 0) return text;
    if (text.charAt(0) === "/") return apiBase() + text;
    return text;
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

  function ensureStudio(node) {
    node.properties = node.properties || {};
    if (!node.properties.ad_studio || typeof node.properties.ad_studio !== "object") {
      node.properties.ad_studio = {};
    }
    return node.properties.ad_studio;
  }

  function resultValues(node) {
    var result = node.properties && node.properties.result && node.properties.result.result;
    if (result && result.values && typeof result.values === "object") return result.values;
    return null;
  }

  function mixHex(fromColor, toColor, amount) {
    function channel(hex, index) {
      return parseInt(hex.substr(index, 2), 16);
    }
    var from = String(fromColor || "#8AB4FF").replace("#", "");
    var to = String(toColor || "#FFFFFF").replace("#", "");
    if (from.length < 6 || to.length < 6) return fromColor || "#8AB4FF";
    var mixed = "#";
    for (var index = 0; index < 6; index += 2) {
      var value = Math.round(channel(from, index) * (1 - amount) + channel(to, index) * amount);
      mixed += ("0" + Math.max(0, Math.min(255, value)).toString(16)).slice(-2);
    }
    return mixed;
  }

  function paintWires(node, color) {
    if (!node.graph || !node.graph.links || !node.inputs) return;
    var productColor = mixHex(color, "#FF7AD9", 0.55);
    node.inputs.forEach(function (input) {
      if (input.link == null) return;
      var link = node.graph.links[input.link];
      if (!link) return;
      if (input.name === "brand_brief") link.color = color;
      if (input.name === "product_image") link.color = productColor;
      if (input.name === "image") link.color = "#7DFFB3";
    });
  }

  function loadImage(node, url) {
    var resolved = resolveUrl(url);
    if (!resolved) return;
    if (node._adImageUrl === resolved && node._adImage) return;
    node._adImageUrl = resolved;
    var image = new Image();
    image.onload = function () {
      if (node._adImageUrl !== resolved) return;
      node._adImage = image;
      if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
    };
    image.onerror = function () {
      node._adImageFailed = resolved;
    };
    image.src = resolved;
  }

  function rememberResult(node) {
    var values = resultValues(node);
    if (!values) return;
    var studio = ensureStudio(node);
    if (values.prompt) studio.prompt = values.prompt;
    if (values.image_url) studio.image_url = values.image_url;
    if (values.image_path) studio.image_path = values.image_path;
    if (values.placeholder != null) studio.placeholder = !!values.placeholder;
    if (values.model) studio.model = values.model;
    if (values.style_id) studio.style_id = values.style_id;
    if (values.style_name) studio.style_name = values.style_name;
    if (values.brand_name) studio.brief = values;
    if (values.image_url) loadImage(node, values.image_url);
    else if (studio.preview_url) loadImage(node, studio.preview_url);
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
  }

  function previewUrl(node) {
    var values = resultValues(node);
    if (values && values.image_url) return values.image_url;
    var studio = ensureStudio(node);
    return studio.image_url || studio.preview_url || "";
  }

  function contentTop(node) {
    var top = 6;
    var widgets = node.widgets || [];
    for (var i = 0; i < widgets.length; i++) {
      var widget = widgets[i];
      if (!widget || widget.type === "ad_hidden" || widget.name === "favorites_json" || widget.name === "variation") {
        continue;
      }
      if (widget.last_y == null) continue;
      var height = widget.computeSize ? widget.computeSize(node.size[0])[1] : 20;
      if (height < 1) continue;
      top = Math.max(top, widget.last_y + height + 8);
    }
    return top;
  }

  function roundRect(ctx, x, y, w, h, radius) {
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(x, y, w, h, radius);
    } else {
      ctx.rect(x, y, w, h);
    }
  }

  function wrapText(ctx, text, maxWidth) {
    var words = String(text || "").split(/\s+/);
    var lines = [];
    var current = "";
    for (var i = 0; i < words.length; i++) {
      var trial = current ? current + " " + words[i] : words[i];
      if (ctx.measureText(trial).width > maxWidth && current) {
        lines.push(current);
        current = words[i];
      } else {
        current = trial;
      }
    }
    if (current) lines.push(current);
    return lines;
  }

  function drawContainedImage(ctx, image, x, y, w, h, discarded) {
    ctx.save();
    roundRect(ctx, x, y, w, h, 10);
    ctx.clip();
    ctx.fillStyle = "#0E1016";
    ctx.fillRect(x, y, w, h);
    if (discarded) ctx.filter = "grayscale(1) brightness(0.72)";
    var scale = Math.min(w / image.width, h / image.height);
    var dw = image.width * scale;
    var dh = image.height * scale;
    ctx.drawImage(image, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    ctx.restore();
  }

  function drawChip(ctx, text, x, y, bg, fg) {
    ctx.save();
    ctx.font = "12px sans-serif";
    var width = ctx.measureText(text).width + 14;
    ctx.fillStyle = bg;
    roundRect(ctx, x, y, width, 18, 9);
    ctx.fill();
    ctx.fillStyle = fg;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x + 7, y + 10);
    ctx.restore();
    return width;
  }

  function hideWidget(widget) {
    widget.type = "ad_hidden";
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

  function collectFavorites(graph) {
    var favorites = [];
    if (!graph || !graph._nodes) return favorites;
    graph._nodes.forEach(function (other) {
      if (!other || other.type !== "ad_studio/AdCreative") return;
      if (other.mode === 2) return;
      var studio = (other.properties && other.properties.ad_studio) || {};
      if (!studio.favorite) return;
      favorites.push({
        style_id: studio.style_id || widgetValue(other, "style_id", ""),
        style_name: studio.style_name || other.title || "",
        prompt: studio.prompt || "",
        image_path: studio.image_path || "",
        image_url: studio.image_url || studio.preview_url || ""
      });
    });
    return favorites;
  }

  function injectFavorites(node) {
    if (!node || node.type !== "ad_studio/AdCreative") return;
    var widget = findWidget(node, "favorites_json");
    if (!widget) return;
    widget.value = JSON.stringify(collectFavorites(node.graph));
  }

  function applyCreativeStyle(node, styleId) {
    var style = STYLE_BY_ID[styleId];
    var studio = ensureStudio(node);
    if (style) {
      studio.style_id = style.id;
      studio.style_name = style.name;
      node.color = style.color || node.color;
      node.title = String(style.name || style.id).toUpperCase();
      paintWires(node, style.color || "#8AB4FF");
    } else {
      paintWires(node, node.color || "#8AB4FF");
    }
  }

  function AdBrandBriefNode() {
    this.serialize_widgets = true;
    this.color = "#7AA2FF";
    this.bgcolor = BODY;
    this.title = "BRAND WEBSITE + PRODUCT NAME";
    addRuleInputs(this);
    this.addOutput("brand_brief", "*");
    this.addWidget("string", "website_url", "https://example.com", function () {}, {});
    this.addWidget("string", "product_name", "Luma Serum", function () {}, {});
    this.addWidget("string", "extra_notes", "", function () {}, {});
    this.hooks = { didExecute: [rememberResult], didLoad: [function (node) { paintWires(node, "#7AA2FF"); }] };
    this.size = AdBrandBriefNode.size.concat();
  }
  AdBrandBriefNode.title = "BRAND WEBSITE + PRODUCT NAME";
  AdBrandBriefNode.desc = "Website URL and product name in, brand brief out.";
  AdBrandBriefNode.size = [480, 320];
  AdBrandBriefNode.prototype.onConfigure = function () {
    var studio = ensureStudio(this);
    if (studio.brief) this._adBrief = studio.brief;
  };
  AdBrandBriefNode.prototype.onDrawForeground = function (ctx) {
    var values = resultValues(this);
    var studio = ensureStudio(this);
    var brief = (values && values.brand_name) ? values : (studio.brief || null);
    var top = contentTop(this);
    ctx.save();
    ctx.font = "13px sans-serif";
    ctx.fillStyle = "#D5D8E0";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    if (!brief) {
      ctx.fillText("Brand site + product name", 16, top);
      ctx.fillStyle = "#8E95A8";
      ctx.fillText("Run the graph to extract tone, claims, and colors.", 16, top + 20);
      ctx.restore();
      return;
    }
    var lines = [
      (brief.brand_name || "Brand") + "  ·  " + (brief.product_name || ""),
      brief.tagline || "",
      brief.tone ? "Tone  " + brief.tone : "",
      brief.audience ? "For  " + brief.audience : "",
      brief.extractor ? "Source  " + brief.extractor : ""
    ].filter(Boolean);
    lines.forEach(function (line, index) {
      ctx.fillText(String(line).slice(0, 64), 16, top + index * 18);
    });
    ctx.restore();
  };

  function AdProductImageNode() {
    var node = this;
    this.serialize_widgets = true;
    this.color = "#FF7AD9";
    this.bgcolor = BODY;
    this.title = "PRODUCT IMAGE";
    addRuleInputs(this);
    this.addOutput("product_image", "*");
    this.addWidget("string", "image_path", "/ad-studio/placeholders/product.png", function (value) {
      ensureStudio(node).preview_url = value;
      loadImage(node, value);
    }, {});
    var upload = this.addWidget("button", "upload", "Upload product photo", function () {
      uploadProduct(node);
    }, { serialize: false });
    upload.label = "Upload product photo";
    this.hooks = { didExecute: [rememberResult] };
    this.size = AdProductImageNode.size.concat();
  }
  AdProductImageNode.title = "PRODUCT IMAGE";
  AdProductImageNode.desc = "Upload or point at the product photo used as the image reference.";
  AdProductImageNode.size = [480, 460];
  AdProductImageNode.prototype.onConfigure = function () {
    var studio = ensureStudio(this);
    var url = studio.image_url || studio.preview_url || widgetValue(this, "image_path", "");
    if (url) loadImage(this, url);
  };
  AdProductImageNode.prototype.onDrawForeground = function (ctx) {
    var top = contentTop(this);
    var width = this.size[0] - 32;
    var height = Math.max(80, this.size[1] - top - 16);
    var image = this._adImage;
    if (image && image.naturalWidth) {
      drawContainedImage(ctx, image, 16, top, width, height, false);
    } else {
      ctx.save();
      ctx.fillStyle = "#11141C";
      roundRect(ctx, 16, top, width, height, 10);
      ctx.fill();
      ctx.fillStyle = "#F0B8D8";
      ctx.font = "16px sans-serif";
      ctx.fillText("PRODUCT IMAGE", 28, top + 24);
      ctx.restore();
    }
    drawChip(ctx, "REFERENCE", 26, top + 10, "rgba(0,0,0,0.72)", "#FFD0EC");
  };

  function uploadProduct(node) {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg,image/webp";
    input.onchange = function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var body = new FormData();
      body.append("image", file, file.name);
      var headersPromise = Promise.resolve({});
      if (root.NeoScaffold && root.NeoScaffold.api && root.NeoScaffold.api.getAuthorizationHeaders) {
        headersPromise = root.NeoScaffold.api.getAuthorizationHeaders();
      }
      headersPromise.then(function (headers) {
        var nextHeaders = Object.assign({}, headers || {});
        delete nextHeaders["Content-Type"];
        return fetch(apiBase() + "/ad-studio/upload", {
          method: "POST",
          body: body,
          headers: nextHeaders
        });
      }).then(function (response) {
        if (!response.ok) throw new Error("upload failed (" + response.status + ")");
        return response.json();
      }).then(function (payload) {
        var widget = findWidget(node, "image_path");
        if (widget) widget.value = payload.url || payload.path;
        var studio = ensureStudio(node);
        studio.preview_url = payload.url;
        studio.image_url = payload.url;
        studio.image_path = payload.path;
        loadImage(node, payload.url);
        if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
      }).catch(function (error) {
        console.error(error);
        alert("Product upload failed: " + error.message);
      });
    };
    input.click();
  }

  function AdCreativeNode() {
    var node = this;
    this.serialize_widgets = true;
    this.color = "#8AB4FF";
    this.bgcolor = BODY;
    this.title = "AD CREATIVE";
    addRuleInputs(this);
    var brand = this.addInput("brand_brief", "brand_brief");
    brand.label = "brand";
    var product = this.addInput("product_image", "product_image");
    product.label = "product";
    this.addOutput("ad", "ad_image");
    this.addWidget("combo", "style_id", STYLE_IDS[0], function (value) {
      applyCreativeStyle(node, value);
    }, { values: STYLE_IDS });
    this.addWidget("combo", "aspect", "style", function () {}, { values: ["style", "1:1", "9:16"] });
    this.addWidget("combo", "refine_prompt", "no", function () {}, { values: ["no", "yes"] });
    hideWidget(this.addWidget("string", "favorites_json", "[]", function () {}, {}));
    hideWidget(this.addWidget("string", "variation", "", function () {}, {}));
    this.hooks = {
      willQueue: [injectFavorites],
      didExecute: [rememberResult],
      didLoad: [function (loaded) {
        applyCreativeStyle(loaded, widgetValue(loaded, "style_id", STYLE_IDS[0]));
      }]
    };
    this.size = AdCreativeNode.size.concat();
    ensureStudio(this);
  }
  AdCreativeNode.title = "Ad Creative";
  AdCreativeNode.desc = "One ad style. Shows the prompt, the still, and Keep / Discard / Favorite.";
  AdCreativeNode.size = [320, 530];
  AdCreativeNode.prototype.onConfigure = function () {
    applyCreativeStyle(this, widgetValue(this, "style_id", STYLE_IDS[0]));
    var url = previewUrl(this);
    if (url) loadImage(this, url);
  };
  AdCreativeNode.prototype.onDrawForeground = function (ctx) {
    var studio = ensureStudio(this);
    var values = resultValues(this) || {};
    var discarded = this.mode === 2 || studio.discarded;
    var favorite = !!studio.favorite && !discarded;
    var top = contentTop(this);
    var margin = 12;
    var buttonRow = 34;
    var promptHeight = 62;
    var imageHeight = Math.max(90, this.size[1] - top - promptHeight - buttonRow - 10);
    var imageWidth = this.size[0] - margin * 2;
    var image = this._adImage;

    if (image && image.naturalWidth) {
      drawContainedImage(ctx, image, margin, top, imageWidth, imageHeight, discarded);
    } else {
      ctx.save();
      ctx.fillStyle = "#11141C";
      roundRect(ctx, margin, top, imageWidth, imageHeight, 10);
      ctx.fill();
      ctx.fillStyle = "#F3F4F6";
      ctx.font = "bold 18px sans-serif";
      ctx.fillText(this.title || "AD", margin + 12, top + 36);
      ctx.fillStyle = "#FF8D8D";
      ctx.fillText("PLACEHOLDER", margin + 12, top + 64);
      ctx.restore();
    }

    drawChip(ctx, "GPT IMAGE 2", margin + 8, top + 8, "rgba(0,0,0,0.78)", "#F4F7FF");
    var placeholder = studio.placeholder || values.placeholder;
    if (placeholder || !(values.image_url)) {
      drawChip(ctx, "PLACEHOLDER", margin + 108, top + 8, "rgba(120, 16, 24, 0.92)", "#FFD0D0");
    }
    if (favorite) {
      drawChip(ctx, "FAVORITE", margin + 8, top + imageHeight - 28, "#146C43", "#E9FFF4");
    }
    if (discarded) {
      ctx.save();
      ctx.fillStyle = "rgba(120, 16, 24, 0.78)";
      ctx.fillRect(margin, top + imageHeight / 2 - 18, imageWidth, 36);
      ctx.fillStyle = "#FFE8E8";
      ctx.font = "bold 16px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("DISCARDED", margin + imageWidth / 2, top + imageHeight / 2);
      ctx.restore();
    }

    var prompt = values.prompt || studio.prompt || "Prompt appears here after a run.";
    ctx.save();
    ctx.font = "12px sans-serif";
    ctx.fillStyle = discarded ? "#8E95A8" : "#E6E8EE";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    var lines = wrapText(ctx, prompt, imageWidth);
    var promptTop = top + imageHeight + 6;
    for (var lineIndex = 0; lineIndex < Math.min(lines.length, 3); lineIndex++) {
      ctx.fillText(lines[lineIndex], margin, promptTop + lineIndex * 15);
    }
    ctx.restore();

    var buttonY = this.size[1] - buttonRow;
    var gap = 6;
    var buttonW = (imageWidth - gap * 2) / 3;
    var buttons = [
      { id: "keep", label: "KEEP", x: margin, fill: "#1E6B45", text: "#E9FFF4" },
      { id: "discard", label: "DISCARD", x: margin + buttonW + gap, fill: discarded ? "#8E2430" : "#A33B46", text: "#FFE8E8" },
      { id: "favorite", label: favorite ? "SAVED" : "FAVORITE", x: margin + (buttonW + gap) * 2, fill: favorite ? "#C6A15B" : "#3A3F4E", text: favorite ? "#221A08" : "#F6E7C1" }
    ];
    this._adButtons = [];
    ctx.save();
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    buttons.forEach(function (button) {
      ctx.fillStyle = button.fill;
      roundRect(ctx, button.x, buttonY, buttonW, 26, 8);
      ctx.fill();
      ctx.fillStyle = button.text;
      ctx.fillText(button.label, button.x + buttonW / 2, buttonY + 13);
      this._adButtons.push({ id: button.id, x: button.x, y: buttonY, w: buttonW, h: 26 });
    }, this);
    ctx.restore();

    ctx.save();
    ctx.lineWidth = favorite || discarded ? 5 : 0;
    if (favorite) ctx.strokeStyle = "#3DDC97";
    if (discarded) ctx.strokeStyle = "#FF5A6A";
    if (favorite || discarded) {
      ctx.strokeRect(2, -26, this.size[0] - 4, this.size[1] + 26);
    }
    ctx.restore();
  };
  AdCreativeNode.prototype.onMouseDown = function (_event, pos) {
    var buttons = this._adButtons || [];
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      if (pos[0] < button.x || pos[0] > button.x + button.w || pos[1] < button.y || pos[1] > button.y + button.h) {
        continue;
      }
      var studio = ensureStudio(this);
      if (button.id === "keep") {
        this.mode = 0;
        studio.discarded = false;
      } else if (button.id === "discard") {
        this.mode = 2;
        studio.discarded = true;
      } else if (button.id === "favorite") {
        if (this.mode === 2) return true;
        studio.favorite = !studio.favorite;
      }
      if (this.setDirtyCanvas) this.setDirtyCanvas(true, true);
      return true;
    }
    return false;
  };

  function AdFrame916Node() {
    this.serialize_widgets = true;
    this.color = "#7DFFB3";
    this.bgcolor = BODY;
    this.title = "TO 9:16";
    addRuleInputs(this);
    var imageInput = this.addInput("image", "ad_image");
    imageInput.label = "ad";
    this.addOutput("vertical", "ad_image");
    this.addWidget("combo", "fit", "cover", function () {}, { values: ["cover", "pad"] });
    this.hooks = { didExecute: [rememberResult], didLoad: [function (node) { paintWires(node, "#7DFFB3"); }] };
    this.size = AdFrame916Node.size.concat();
  }
  AdFrame916Node.title = "TO 9:16";
  AdFrame916Node.desc = "Cover-crop or pad an ad to 1080x1920 without calling the image model.";
  AdFrame916Node.size = [320, 620];
  AdFrame916Node.prototype.onConfigure = function () {
    var url = previewUrl(this);
    if (url) loadImage(this, url);
    paintWires(this, "#7DFFB3");
  };
  AdFrame916Node.prototype.onDrawForeground = function (ctx) {
    var top = contentTop(this);
    var margin = 12;
    var width = this.size[0] - margin * 2;
    var height = Math.max(120, this.size[1] - top - 28);
    var image = this._adImage;
    if (image && image.naturalWidth) {
      drawContainedImage(ctx, image, margin, top, width, height, false);
    } else {
      ctx.save();
      ctx.fillStyle = "#11141C";
      roundRect(ctx, margin, top, width, height, 10);
      ctx.fill();
      ctx.fillStyle = "#D8FFE8";
      ctx.font = "bold 18px sans-serif";
      ctx.fillText("9:16", margin + 12, top + 36);
      ctx.restore();
    }
    drawChip(ctx, "1080 x 1920", margin + 8, top + 8, "rgba(0,0,0,0.78)", "#D8FFE8");
    ctx.save();
    ctx.fillStyle = "#C9D0DE";
    ctx.font = "12px sans-serif";
    ctx.fillText("Converts the connected ad to vertical.", margin, this.size[1] - 18);
    ctx.restore();
  };

  root.NeoScaffoldExtras.nodes["ad_studio/AdBrandBrief"] = AdBrandBriefNode;
  root.NeoScaffoldExtras.nodes["ad_studio/AdProductImage"] = AdProductImageNode;
  root.NeoScaffoldExtras.nodes["ad_studio/AdCreative"] = AdCreativeNode;
  root.NeoScaffoldExtras.nodes["ad_studio/AdFrame916"] = AdFrame916Node;

  if (typeof LiteGraph !== "undefined" && LiteGraph.registerNodeType) {
    LiteGraph.registerNodeType("ad_studio/AdBrandBrief", AdBrandBriefNode);
    LiteGraph.registerNodeType("ad_studio/AdProductImage", AdProductImageNode);
    LiteGraph.registerNodeType("ad_studio/AdCreative", AdCreativeNode);
    LiteGraph.registerNodeType("ad_studio/AdFrame916", AdFrame916Node);
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
