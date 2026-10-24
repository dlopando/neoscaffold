"""Editable library of static ad styles.

Change copy, aspect, or color here. `styles.json` is regenerated from this
list by ``python -m custom_extensions.ad_studio.build_workflow`` so the
workflow generator and the HTTP style endpoint stay in sync. Prefer editing
this file, then regenerate.
"""

STYLES = [
    {
        "id": "claymation",
        "name": "Claymation",
        "aspect": "1:1",
        "color": "#E39B6A",
        "headline": "",
        "template": (
            "Stop-motion claymation still of {product_name} by {brand_name}. "
            "The real product sits in a tactile clay world with fingerprint "
            "texture, tiny fabric set, soft studio light, and a handmade shadow. "
            "Tone: {tone}. Audience: {audience}."
        ),
    },
    {
        "id": "imessage_thread",
        "name": "iMessage Thread",
        "aspect": "1:1",
        "color": "#6FCF97",
        "headline": "",
        "template": (
            "A realistic iPhone iMessage screenshot advertising {product_name}. "
            "Blue and gray bubbles, a friend freaking out in a good way, the "
            "product photo pinned in the thread. Contact name is a first name. "
            "Brand voice: {tone}. Claims to echo, not invent: {claims}."
        ),
    },
    {
        "id": "fake_tweet",
        "name": "Fake Tweet",
        "aspect": "1:1",
        "color": "#8EC8FF",
        "headline": "",
        "template": (
            "A realistic X post screenshot. A sharp, slightly unhinged tweet "
            "about {product_name} from {brand_name}, with the product photo "
            "attached below the text. Include a display name, handle, and "
            "like count. Tone: {tone}."
        ),
    },
    {
        "id": "dont_buy_this",
        "name": "Don't Buy This",
        "aspect": "1:1",
        "color": "#FF5A5A",
        "headline": "DON'T BUY THIS {product_name}",
        "template": (
            "Bold contrarian poster. Huge condensed headline, the real product "
            "dead center, lots of negative space, black and {colors}. "
            "The joke is confidence: we are daring you not to want it. "
            "Category: {category}."
        ),
    },
    {
        "id": "eight_signs",
        "name": "8 Signs",
        "aspect": "1:1",
        "color": "#F2C14E",
        "headline": "8 SIGNS",
        "template": (
            "Listicle thumbnail ad. Giant '8 SIGNS' headline and a smaller "
            "line about {product_name} for {audience}. The real product is "
            "held in the corner like a YouTube thumbnail. High contrast, "
            "yellow highlight, {tone}."
        ),
    },
    {
        "id": "ninety_seven",
        "name": "97 Percent",
        "aspect": "1:1",
        "color": "#7DFFB3",
        "headline": "97%",
        "template": (
            "Stat-led ad. Enormous '97%' and a short honest qualifier drawn "
            "from these claims: {claims}. {product_name} by {brand_name} "
            "photographed on a clean plinth. Colors: {colors}."
        ),
    },
    {
        "id": "were_so_sorry",
        "name": "We're So Sorry",
        "aspect": "1:1",
        "color": "#FF8FB1",
        "headline": "WE'RE SO SORRY!",
        "template": (
            "Apology-ad poster. Huge 'WE'RE SO SORRY!' as if {brand_name} "
            "cannot keep {product_name} in stock. The real product is the "
            "hero, slightly chaotic paper texture, {tone}."
        ),
    },
    {
        "id": "notes_app",
        "name": "Notes App",
        "aspect": "1:1",
        "color": "#F7E7A1",
        "headline": "",
        "template": (
            "iOS Notes app screenshot. A late-night confession about "
            "{product_name}, yellow note paper, the product photo pasted "
            "under the text. Audience: {audience}. Tagline energy: {tagline}."
        ),
    },
    {
        "id": "reddit_post",
        "name": "Reddit Post",
        "aspect": "1:1",
        "color": "#FF7A3C",
        "headline": "",
        "template": (
            "Reddit post screenshot in a skincare or product subreddit. "
            "Title is a skeptical question about {product_name}. The real "
            "product is the image. Upvotes visible. Tone: {tone}."
        ),
    },
    {
        "id": "google_review",
        "name": "5-Star Review",
        "aspect": "1:1",
        "color": "#FFD166",
        "headline": "",
        "template": (
            "Google review card with five stars for {brand_name}. Short "
            "review quoting the spirit of: {claims}. Product photo beside "
            "the stars. Clean white card on a soft gray desk."
        ),
    },
    {
        "id": "group_chat",
        "name": "Group Chat",
        "aspect": "1:1",
        "color": "#B388FF",
        "headline": "",
        "template": (
            "Three-person group chat losing their minds about {product_name}. "
            "Mixed bubble colors, one person sends the product photo, another "
            "replies in all caps. Audience: {audience}."
        ),
    },
    {
        "id": "bold_headline",
        "name": "Bold Headline",
        "aspect": "1:1",
        "color": "#FFFFFF",
        "headline": "{product_name}",
        "template": (
            "Swiss-bold print ad. One massive wordmark built from the product "
            "name, the real bottle or pack locked to a grid, colors {colors}, "
            "tone {tone}. Almost no other copy."
        ),
    },
    {
        "id": "ugc_selfie",
        "name": "UGC Selfie",
        "aspect": "1:1",
        "color": "#F4A7C4",
        "headline": "",
        "template": (
            "Handheld selfie, bathroom or bedroom light, a real person "
            "holding the actual {product_name} close to camera. Imperfect "
            "framing, no studio gloss. For {audience}. Tagline mood: {tagline}."
        ),
    },
    {
        "id": "before_after",
        "name": "Before / After",
        "aspect": "1:1",
        "color": "#9BE7FF",
        "headline": "BEFORE / AFTER",
        "template": (
            "Split frame labeled BEFORE / AFTER. The real {product_name} "
            "straddles the divide. The change is environmental and emotional, "
            "not a medical claim beyond: {claims}."
        ),
    },
    {
        "id": "ingredient_macro",
        "name": "Ingredient Macro",
        "aspect": "1:1",
        "color": "#A8E06A",
        "headline": "",
        "template": (
            "Extreme macro still life. The real product surrounded by the "
            "raw ingredients suggested by {category} and {differentiators}. "
            "Dew, texture, shallow depth of field. Colors {colors}."
        ),
    },
    {
        "id": "newspaper",
        "name": "Newspaper Ad",
        "aspect": "1:1",
        "color": "#E7E2D6",
        "headline": "",
        "template": (
            "Black-and-white newspaper advertisement, halftone, column rules. "
            "{brand_name} announces {product_name}. Headline energy from "
            "{tagline}. The product is a crisp halftone photo."
        ),
    },
    {
        "id": "subway_poster",
        "name": "Subway Poster",
        "aspect": "1:1",
        "color": "#FF6B6B",
        "headline": "",
        "template": (
            "A poster on a subway wall, shot straight on, slightly grimy "
            "tiles around the frame. Poster sells {product_name} to "
            "{audience} with tone {tone}. The real product is large."
        ),
    },
    {
        "id": "billboard",
        "name": "Billboard",
        "aspect": "1:1",
        "color": "#7AA2FF",
        "headline": "",
        "template": (
            "A city billboard at dusk photographed from across the street. "
            "The board is a simple ad for {product_name} by {brand_name}. "
            "Tagline: {tagline}. Wet asphalt reflections."
        ),
    },
    {
        "id": "unboxing",
        "name": "Unboxing",
        "aspect": "1:1",
        "color": "#D7B59A",
        "headline": "",
        "template": (
            "Overhead unboxing. Tissue paper, a just-opened mailer, the real "
            "{product_name} revealed. Hands at the edge of frame. "
            "Differentiators to hint at: {differentiators}."
        ),
    },
    {
        "id": "meme_reaction",
        "name": "Reaction Meme",
        "aspect": "1:1",
        "color": "#C9F26D",
        "headline": "",
        "template": (
            "Two-panel reaction meme. Top: skepticism about the category "
            "{category}. Bottom: the real {product_name} and a short caption "
            "in the tone {tone}. White impact-style caption, not a collage "
            "of other ads."
        ),
    },
    {
        "id": "packaging_flatlay",
        "name": "Flat Lay",
        "aspect": "1:1",
        "color": "#F3D1C6",
        "headline": "",
        "template": (
            "Editorial flat lay on colored paper {colors}. {product_name} "
            "centered, a few props that signal {audience}, hard shadow, "
            "perfectly square crop."
        ),
    },
    {
        "id": "neon_night",
        "name": "Neon Night",
        "aspect": "1:1",
        "color": "#FF4DFF",
        "headline": "",
        "template": (
            "Nighttime product portrait. Neon magenta and cyan, the real "
            "{product_name} on black acrylic, reflections, club energy, "
            "still a single product shot. Tone: {tone}."
        ),
    },
    {
        "id": "editorial",
        "name": "Editorial",
        "aspect": "1:1",
        "color": "#E8E4DC",
        "headline": "",
        "template": (
            "Fashion-magazine still. Generous margins, a serif caption "
            "'{brand_name}', the real product styled like jewelry. "
            "Tagline as the deck: {tagline}."
        ),
    },
    {
        "id": "infographic_stat",
        "name": "Stat Card",
        "aspect": "1:1",
        "color": "#5CE1E6",
        "headline": "",
        "template": (
            "One-stat infographic card. Pull a single number only if it "
            "appears in the claims ({claims}); otherwise use a qualitative "
            "badge. {product_name} sits in a circular crop. Colors {colors}."
        ),
    },
    {
        "id": "checklist",
        "name": "Checklist",
        "aspect": "1:1",
        "color": "#8BE38B",
        "headline": "",
        "template": (
            "Hand-checked checklist ad. Three boxes ticked using only facts "
            "from: {claims}. {differentiators}. The real product stamped at "
            "the bottom like a seal for {brand_name}."
        ),
    },
    {
        "id": "myth_fact",
        "name": "Myth vs Fact",
        "aspect": "1:1",
        "color": "#FF9F68",
        "headline": "MYTH VS FACT",
        "template": (
            "Two-column MYTH VS FACT card about {category}. Facts may only "
            "paraphrase: {claims}. Do not invent studies. Product photo "
            "bridges the columns."
        ),
    },
    {
        "id": "founder_letter",
        "name": "Founder Letter",
        "aspect": "1:1",
        "color": "#E7D3B0",
        "headline": "",
        "template": (
            "A typed letter on warm paper from the founder of {brand_name} "
            "about why {product_name} exists for {audience}. Short paragraphs, "
            "a signature, the product photographed on the letter."
        ),
    },
    {
        "id": "limited_drop",
        "name": "Limited Drop",
        "aspect": "1:1",
        "color": "#F25C54",
        "headline": "LIMITED DROP",
        "template": (
            "Drop culture poster. 'LIMITED DROP' plus {product_name}. "
            "Sticker shadows, barcode, the real product like a collab object. "
            "Tone: {tone}."
        ),
    },
    {
        "id": "vintage_print",
        "name": "Vintage Print",
        "aspect": "1:1",
        "color": "#E0A96D",
        "headline": "",
        "template": (
            "1960s print ad, slightly misregistered inks, {brand_name} "
            "selling {product_name}. Illustration style around a photographic "
            "product that must stay the real object. Tagline: {tagline}."
        ),
    },
    {
        "id": "y2k_gloss",
        "name": "Y2K Gloss",
        "aspect": "1:1",
        "color": "#FF71CE",
        "headline": "",
        "template": (
            "Y2K beauty ad. Chrome type, star glints, baby-blue and hot-pink, "
            "the real {product_name} looking expensive and a little ridiculous. "
            "Audience: {audience}."
        ),
    },
    {
        "id": "swiss_minimal",
        "name": "Swiss Minimal",
        "aspect": "1:1",
        "color": "#F5F5F5",
        "headline": "",
        "template": (
            "Strict Swiss layout. One red accent, Helvetica-like type, the "
            "product name {product_name}, brand {brand_name}, and a perfectly "
            "lit product photo. Nothing else."
        ),
    },
    {
        "id": "receipt_joke",
        "name": "Receipt Joke",
        "aspect": "1:1",
        "color": "#F4F1EA",
        "headline": "",
        "template": (
            "A long thermal receipt as the ad. Line items joke about trying "
            "every other {category} before {product_name}. The real product "
            "sits on the receipt. Tone: {tone}."
        ),
    },
    {
        "id": "story_hook_916",
        "name": "Story Hook",
        "aspect": "9:16",
        "color": "#FF4D6D",
        "headline": "WAIT",
        "template": (
            "Vertical 9:16 story frame. Giant 'WAIT' at the top, the real "
            "{product_name} in the middle third, a one-line hook for "
            "{audience} at the bottom. Safe margins for a phone UI."
        ),
    },
    {
        "id": "reel_apology_916",
        "name": "Vertical Apology",
        "aspect": "9:16",
        "color": "#FF8BA7",
        "headline": "WE'RE SO SORRY!",
        "template": (
            "Vertical 9:16. 'WE'RE SO SORRY!' stacked huge, then the real "
            "product, then a tiny line that {brand_name} sold through the "
            "last batch. Designed as a reel cover."
        ),
    },
    {
        "id": "vertical_tweet_916",
        "name": "Vertical Tweet",
        "aspect": "9:16",
        "color": "#9AD1FF",
        "headline": "",
        "template": (
            "Vertical 9:16 phone screenshot of an X post about {product_name}, "
            "the attached photo is the real product, plenty of black bezel "
            "so it reads as a phone in a story."
        ),
    },
    {
        "id": "vertical_imessage_916",
        "name": "Vertical iMessage",
        "aspect": "9:16",
        "color": "#62D68A",
        "headline": "",
        "template": (
            "Vertical 9:16 full-phone iMessage thread. The conversation "
            "builds to someone sending a photo of the real {product_name}. "
            "Tone: {tone}."
        ),
    },
    {
        "id": "pov_shelf_916",
        "name": "POV Shelf",
        "aspect": "9:16",
        "color": "#CDB4FF",
        "headline": "POV:",
        "template": (
            "Vertical 9:16 POV shot looking at a bathroom shelf. Caption "
            "'POV:' and a short line for {audience}. The real {product_name} "
            "is the only thing in focus."
        ),
    },
    {
        "id": "green_screen_916",
        "name": "Green Screen Caption",
        "aspect": "9:16",
        "color": "#3DDC97",
        "headline": "",
        "template": (
            "Vertical 9:16 creator frame. A person mid-sentence points beside "
            "a floating picture-in-picture of the real {product_name}. "
            "One burned-in caption, three words max, tone {tone}."
        ),
    },
    {
        "id": "street_interview_916",
        "name": "Street Interview",
        "aspect": "9:16",
        "color": "#FFB703",
        "headline": "",
        "template": (
            "Vertical 9:16 street interview still. Microphone in frame, "
            "a stranger holding the real {product_name}, caption quotes a "
            "short reaction. City background, natural light."
        ),
    },
    {
        "id": "split_caption_916",
        "name": "Split Caption",
        "aspect": "9:16",
        "color": "#48BFE3",
        "headline": "8 SIGNS",
        "template": (
            "Vertical 9:16. Top half is the headline '8 SIGNS', bottom half "
            "is the real {product_name} on a bold color field {colors}. "
            "Built to be cropped no further."
        ),
    },
]
