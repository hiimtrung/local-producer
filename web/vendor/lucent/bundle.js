/* @ds-bundle: {"format":4,"namespace":"Lucent","components":[{"name":"Glass"},{"name":"Card"},{"name":"Button"},{"name":"IconButton"},{"name":"TextField"},{"name":"TextArea"},{"name":"Select"},{"name":"ComboBox"},{"name":"SearchBox"},{"name":"AsyncSearchBox"},{"name":"Checkbox"},{"name":"RadioGroup"},{"name":"Switch"},{"name":"Slider"},{"name":"SegmentedControl"},{"name":"Tabs"},{"name":"NavBar"},{"name":"List"},{"name":"Badge"},{"name":"Progress"},{"name":"Tooltip"},{"name":"Toast"},{"name":"Dialog"}]} */
(function () {
  "use strict";
  var React = window.React;
  var h = React.createElement;
  var useState = React.useState, useRef = React.useRef, useEffect = React.useEffect,
      useMemo = React.useMemo, useCallback = React.useCallback, useId = React.useId;

  /* ---------------- helpers ---------------- */
  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(" ");
  }
  function omit(obj, keys) {
    var r = {};
    for (var k in obj) if (Object.prototype.hasOwnProperty.call(obj, k) && keys.indexOf(k) < 0) r[k] = obj[k];
    return r;
  }
  function assign() { return Object.assign.apply(Object, [{}].concat([].slice.call(arguments))); }
  function useControlled(value, defaultValue) {
    var st = useState(defaultValue);
    var controlled = value !== undefined;
    return [controlled ? value : st[0], function (v) { if (!controlled) st[1](v); }];
  }
  function useStableId(id, prefix) { var gen = useId(); return id || (prefix || "lg") + gen.replace(/:/g, ""); }
  /* Diacritic-insensitive normalize (Vietnamese friendly: "Đà Nẵng" ~ "da nang") */
  function norm(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  }
  function highlight(label, query) {
    if (!query) return label;
    var L = String(label), nl = norm(L), nq = norm(query);
    var i = nl.indexOf(nq);
    if (i < 0 || nl.length !== L.length) return L;
    return [L.slice(0, i), h("mark", { key: "m" }, L.slice(i, i + nq.length)), L.slice(i + nq.length)];
  }
  function useOutside(ref, open, onClose) {
    useEffect(function () {
      if (!open) return;
      function onDown(e) { if (ref.current && !ref.current.contains(e.target)) onClose(); }
      document.addEventListener("mousedown", onDown);
      document.addEventListener("touchstart", onDown);
      return function () { document.removeEventListener("mousedown", onDown); document.removeEventListener("touchstart", onDown); };
    }, [open]);
  }
  function normOptions(options) {
    return (options || []).map(function (o) {
      return typeof o === "object" && o !== null ? o : { value: o, label: String(o) };
    });
  }
  function nextEnabled(opts, from, dir) {
    var n = opts.length; if (!n) return -1;
    var i = from;
    for (var k = 0; k < n; k++) {
      i = (i + dir + n) % n;
      if (!opts[i].disabled) return i;
    }
    return -1;
  }

  /* ---------------- Icon ---------------- */
  var PATHS = {
    search: [["circle", { cx: 10.5, cy: 10.5, r: 6.5 }], ["path", { d: "M15.5 15.5 20 20" }]],
    close: [["path", { d: "M6 6l12 12M18 6 6 18" }]],
    "close-circle": [["circle", { cx: 12, cy: 12, r: 9, fill: "currentColor", stroke: "none" }], ["path", { d: "M9 9l6 6M15 9l-6 6", stroke: "var(--bg-elevated)" }]],
    "chevron-down": [["path", { d: "M6 9l6 6 6-6" }]],
    "chevron-right": [["path", { d: "M9 6l6 6-6 6" }]],
    "chevron-left": [["path", { d: "M15 6l-6 6 6 6" }]],
    "chevron-updown": [["path", { d: "M8 9.5l4-4 4 4M8 14.5l4 4 4-4" }]],
    check: [["path", { d: "M5 12.5l4.5 4.5L19 7.5" }]],
    minus: [["path", { d: "M6 12h12" }]],
    plus: [["path", { d: "M12 5v14M5 12h14" }]],
    info: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 11v5M12 8h.01" }]],
    "check-circle": [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M8 12.5l2.7 2.7L16 9.8" }]],
    warning: [["path", { d: "M12 4 2.8 19.5h18.4z" }], ["path", { d: "M12 10v4M12 16.8h.01" }]],
    error: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 7.5v5.5M12 16.2h.01" }]],
    home: [["path", { d: "M4 10.5 12 4l8 6.5V20h-5v-5h-6v5H4z" }]],
    person: [["circle", { cx: 12, cy: 8, r: 3.6 }], ["path", { d: "M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" }]],
    gear: [["circle", { cx: 12, cy: 12, r: 3 }], ["path", { d: "M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" }]],
    bell: [["path", { d: "M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" }], ["path", { d: "M10 20.5a2 2 0 0 0 4 0" }]],
    heart: [["path", { d: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" }]],
    share: [["path", { d: "M12 3v12M8 7l4-4 4 4M5 12v7h14v-7" }]],
    trash: [["path", { d: "M4.5 7h15M9 7V4.5h6V7M6.5 7l1 13h9l1-13" }]],
    pin: [["path", { d: "M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z" }], ["circle", { cx: 12, cy: 10, r: 2.2 }]],
    wifi: [["path", { d: "M3.5 9a12 12 0 0 1 17 0M6.5 12.2a7.5 7.5 0 0 1 11 0M9.5 15.3a3 3 0 0 1 5 0M12 18.6h.01" }]],
    moon: [["path", { d: "M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z" }]]
  };
  function Icon(props) {
    var size = props.size || 18, parts = PATHS[props.name] || [];
    return h("svg", {
      className: cx("lg-icon", props.className), width: size, height: size, viewBox: "0 0 24 24",
      fill: "none", stroke: "currentColor", strokeWidth: props.strokeWidth || 2,
      strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": props.label ? undefined : true,
      role: props.label ? "img" : undefined, "aria-label": props.label
    }, parts.map(function (p, i) { return h(p[0], assign(p[1], { key: i })); }));
  }
  function renderIcon(ic, size) { return typeof ic === "string" ? h(Icon, { name: ic, size: size }) : ic; }

  function Spinner(props) {
    return h("span", { className: cx("lg-spinner", props.size === "lg" && "lg-spinner--lg"), role: "status", "aria-label": props.label || "Loading" });
  }

  /* ---------------- Glass & Card ---------------- */
  function Glass(props) {
    var variant = props.variant || "regular";
    var rest = omit(props, ["as", "variant", "radius", "floating", "className", "children"]);
    return h(props.as || "div", assign(rest, {
      className: cx("lg-glass", variant !== "regular" && "lg-glass--" + variant, props.floating && "lg-glass--float",
        "lg-r-" + (props.radius || "lg"), props.className)
    }), props.children);
  }
  function Card(props) {
    var rest = omit(props, ["title", "subtitle", "footer", "variant", "children", "className"]);
    return h(Glass, assign(rest, { variant: props.variant || "regular", radius: "lg", className: cx("lg-card", props.className) }),
      props.title ? h("h3", { className: "lg-card__title" }, props.title) : null,
      props.subtitle ? h("p", { className: "lg-card__subtitle" }, props.subtitle) : null,
      props.children,
      props.footer ? h("div", { className: "lg-card__footer" }, props.footer) : null);
  }

  /* ---------------- Buttons ---------------- */
  function Button(props) {
    var variant = props.variant || "glass", size = props.size || "md";
    var rest = omit(props, ["variant", "size", "icon", "iconEnd", "block", "loading", "className", "children"]);
    return h("button", assign({ type: "button" }, rest, {
      className: cx("lg-btn", variant === "glass" ? "lg-glass" : "lg-btn--" + variant, size !== "md" && "lg-btn--" + size,
        props.block && "lg-btn--block", props.className),
      disabled: props.disabled || props.loading, "aria-busy": props.loading || undefined
    }), props.loading ? h(Spinner, null) : props.icon ? renderIcon(props.icon, size === "lg" ? 20 : 17) : null,
      props.children, props.iconEnd ? renderIcon(props.iconEnd, 17) : null);
  }
  function IconButton(props) {
    var variant = props.variant || "glass", size = props.size || "md";
    var rest = omit(props, ["variant", "size", "icon", "label", "className"]);
    return h("button", assign({ type: "button" }, rest, {
      "aria-label": props.label, title: props.label,
      className: cx("lg-iconbtn", variant === "glass" ? "lg-glass" : "lg-iconbtn--" + variant, size !== "md" && "lg-iconbtn--" + size, props.className)
    }), renderIcon(props.icon, size === "sm" ? 16 : size === "lg" ? 22 : 19));
  }

  /* ---------------- Field shell ---------------- */
  function FieldShell(p) {
    return h("div", { className: cx("lg-field", p.className) },
      p.label ? h("label", { className: "lg-label", htmlFor: p.htmlFor, id: p.labelId }, p.label,
        p.required ? h("span", { className: "lg-label__req", "aria-hidden": true }, "*") : null) : null,
      p.children,
      p.error ? h("p", { className: "lg-error", id: p.descId, role: "alert" }, h(Icon, { name: "error", size: 14 }), p.error)
        : (p.hint || p.counter) ? h("p", { className: "lg-hint", id: p.descId }, h("span", null, p.hint), p.counter || null) : null);
  }

  /* ---------------- TextField ---------------- */
  function TextField(props) {
    var id = useStableId(props.id, "tf");
    var st = useControlled(props.value, props.defaultValue !== undefined ? props.defaultValue : "");
    var value = st[0], setValue = st[1];
    var inputRef = useRef(null);
    var size = props.size || "md";
    var descId = (props.hint || props.error) ? id + "-desc" : undefined;
    var rest = omit(props, ["id", "label", "hint", "error", "value", "defaultValue", "onChange", "leading", "trailing", "clearable", "size", "className", "required"]);
    function change(v, e) { setValue(v); if (props.onChange) props.onChange(v, e); }
    return h(FieldShell, { label: props.label, hint: props.hint, error: props.error, htmlFor: id, descId: descId, required: props.required, className: props.className },
      h("div", { className: cx("lg-inputwrap", size !== "md" && "lg-inputwrap--" + size, props.error && "lg-inputwrap--invalid", props.disabled && "lg-inputwrap--disabled") },
        props.leading ? h("span", { className: "lg-inputwrap__lead" }, renderIcon(props.leading, 18)) : null,
        h("input", assign({ type: "text" }, rest, {
          id: id, ref: inputRef, className: "lg-input", value: value, required: props.required,
          "aria-invalid": props.error ? true : undefined, "aria-describedby": descId,
          onChange: function (e) { change(e.target.value, e); }
        })),
        props.clearable && value && !props.disabled ? h("button", {
          type: "button", className: "lg-clear", "aria-label": "Clear",
          onClick: function () { change(""); if (inputRef.current) inputRef.current.focus(); }
        }, h(Icon, { name: "close-circle", size: 18 })) : null,
        props.trailing || null));
  }

  /* ---------------- TextArea ---------------- */
  function TextArea(props) {
    var id = useStableId(props.id, "ta");
    var st = useControlled(props.value, props.defaultValue !== undefined ? props.defaultValue : "");
    var value = st[0], setValue = st[1];
    var ref = useRef(null);
    var autoGrow = props.autoGrow !== false;
    var descId = (props.hint || props.error || props.maxLength) ? id + "-desc" : undefined;
    useEffect(function () {
      if (!autoGrow || !ref.current) return;
      var el = ref.current; el.style.height = "auto";
      var max = props.maxRows ? props.maxRows * 22 + 26 : Infinity;
      el.style.height = Math.min(el.scrollHeight + 2, max) + "px";
      el.style.overflowY = el.scrollHeight + 2 > max ? "auto" : "hidden";
    }, [value, autoGrow]);
    var len = String(value).length;
    var counter = props.maxLength ? h("span", { className: cx("lg-count", len > props.maxLength && "lg-count--over"), "aria-live": "polite" }, len + " / " + props.maxLength) : null;
    var rest = omit(props, ["id", "label", "hint", "error", "value", "defaultValue", "onChange", "autoGrow", "maxRows", "className", "maxLength", "required"]);
    return h(FieldShell, { label: props.label, hint: props.hint, error: props.error, htmlFor: id, descId: descId, required: props.required, counter: counter, className: props.className },
      h("textarea", assign({ rows: 3 }, rest, {
        id: id, ref: ref, value: value, required: props.required,
        className: cx("lg-textarea", autoGrow && "lg-textarea--auto"),
        "aria-invalid": props.error || len > (props.maxLength || Infinity) ? true : undefined, "aria-describedby": descId,
        onChange: function (e) { setValue(e.target.value); if (props.onChange) props.onChange(e.target.value, e); }
      })));
  }

  /* ---------------- Listbox (shared by Select, ComboBox, AsyncSearchBox) ---------------- */
  function Listbox(p) {
    var listRef = useRef(null);
    useEffect(function () {
      if (p.active < 0 || !listRef.current) return;
      var el = listRef.current.querySelector('[data-index="' + p.active + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
    }, [p.active]);
    var body;
    if (p.status) body = h("li", { className: cx("lg-menu__status", p.statusTone === "error" && "lg-menu__status--error"), role: "presentation" }, p.statusIcon || null, p.status);
    else body = p.options.map(function (o, i) {
      var selected = p.selected !== undefined && o.value === p.selected;
      return h("li", {
        key: String(o.value), id: p.id + "-opt-" + i, "data-index": i, role: "option",
        "aria-selected": selected, "aria-disabled": o.disabled || undefined,
        className: cx("lg-option", i === p.active && "lg-option--active", selected && "lg-option--selected"),
        onMouseDown: function (e) { e.preventDefault(); },
        onMouseEnter: function () { if (!o.disabled) p.onHover(i); },
        onClick: function () { if (!o.disabled) p.onPick(o, i); }
      },
        p.showCheck !== false ? h("span", { className: "lg-option__check" }, selected ? h(Icon, { name: "check", size: 16, strokeWidth: 2.5 }) : null) : null,
        o.icon ? renderIcon(o.icon, 18) : null,
        h("span", { className: "lg-option__text" },
          h("span", null, highlight(o.label, p.query)),
          o.description ? h("span", { className: "lg-option__desc" }, o.description) : null));
    });
    return h("div", { className: "lg-popover" },
      h("ul", { ref: listRef, id: p.id, role: "listbox", "aria-labelledby": p.labelledBy, className: "lg-menu lg-glass lg-glass--thick lg-glass--float" }, body));
  }

  /* ---------------- Select ---------------- */
  function Select(props) {
    var id = useStableId(props.id, "sel");
    var options = useMemo(function () { return normOptions(props.options); }, [props.options]);
    var st = useControlled(props.value, props.defaultValue);
    var value = st[0], setValue = st[1];
    var openSt = useState(!!props.defaultOpen), open = openSt[0], setOpen = openSt[1];
    var actSt = useState(-1), active = actSt[0], setActive = actSt[1];
    var wrapRef = useRef(null), btnRef = useRef(null), typed = useRef({ s: "", t: 0 });
    var size = props.size || "md";
    var current = options.filter(function (o) { return o.value === value; })[0];
    var listId = id + "-list", labelId = id + "-label";
    var descId = (props.hint || props.error) ? id + "-desc" : undefined;
    useOutside(wrapRef, open, function () { setOpen(false); });
    function openMenu() {
      var idx = options.indexOf(current);
      setActive(idx >= 0 ? idx : nextEnabled(options, -1, 1)); setOpen(true);
    }
    function pick(o) {
      setValue(o.value); if (props.onChange) props.onChange(o.value, o);
      setOpen(false); if (btnRef.current) btnRef.current.focus();
    }
    function onKey(e) {
      if (props.disabled) return;
      var k = e.key;
      if (!open) {
        if (k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === " ") { e.preventDefault(); openMenu(); }
        return;
      }
      if (k === "ArrowDown") { e.preventDefault(); setActive(nextEnabled(options, active, 1)); }
      else if (k === "ArrowUp") { e.preventDefault(); setActive(nextEnabled(options, active, -1)); }
      else if (k === "Home") { e.preventDefault(); setActive(nextEnabled(options, -1, 1)); }
      else if (k === "End") { e.preventDefault(); setActive(nextEnabled(options, 0, -1)); }
      else if (k === "Enter" || k === " ") { e.preventDefault(); if (options[active]) pick(options[active]); }
      else if (k === "Escape" || k === "Tab") { setOpen(false); }
      else if (k.length === 1) {
        var now = Date.now(); typed.current.s = (now - typed.current.t > 600 ? "" : typed.current.s) + norm(k); typed.current.t = now;
        for (var i = 0; i < options.length; i++) if (!options[i].disabled && norm(options[i].label).indexOf(typed.current.s) === 0) { setActive(i); break; }
      }
    }
    return h(FieldShell, { label: props.label, hint: props.hint, error: props.error, htmlFor: id, labelId: labelId, descId: descId, required: props.required, className: props.className },
      h("div", { ref: wrapRef, style: { position: "relative" } },
        h("button", {
          type: "button", id: id, ref: btnRef, disabled: props.disabled, name: props.name,
          role: "combobox", "aria-haspopup": "listbox", "aria-expanded": open, "aria-controls": listId,
          "aria-labelledby": props.label ? labelId + " " + id : undefined, "aria-label": props.label ? undefined : props["aria-label"],
          "aria-activedescendant": open && active >= 0 ? listId + "-opt-" + active : undefined,
          "aria-invalid": props.error ? true : undefined, "aria-describedby": descId,
          className: cx("lg-inputwrap lg-select-trigger", size !== "md" && "lg-inputwrap--" + size, props.error && "lg-inputwrap--invalid", props.disabled && "lg-inputwrap--disabled"),
          onClick: function () { open ? setOpen(false) : openMenu(); }, onKeyDown: onKey
        },
          current && current.icon ? renderIcon(current.icon, 18) : null,
          h("span", { className: cx("lg-select-trigger__value", !current && "lg-select-trigger__value--placeholder") }, current ? current.label : (props.placeholder || "Select…")),
          h("span", { className: "lg-chevron" }, h(Icon, { name: "chevron-updown", size: 16 }))),
        open ? h(Listbox, {
          id: listId, labelledBy: props.label ? labelId : undefined, options: options, active: active, selected: value,
          onHover: setActive, onPick: pick, status: options.length ? null : "No options"
        }) : null));
  }

  /* ---------------- ComboBox ---------------- */
  function ComboBox(props) {
    var id = useStableId(props.id, "cb");
    var options = useMemo(function () { return normOptions(props.options); }, [props.options]);
    var st = useControlled(props.value, props.defaultValue);
    var value = st[0], setValue = st[1];
    var current = options.filter(function (o) { return o.value === value; })[0];
    var qSt = useState(current ? current.label : (value != null && props.allowCustom ? String(value) : "")), query = qSt[0], setQuery = qSt[1];
    var openSt = useState(!!props.defaultOpen), open = openSt[0], setOpen = openSt[1];
    var typingSt = useState(!!props.defaultOpen && !!props.defaultQuery), typing = typingSt[0], setTyping = typingSt[1];
    var actSt = useState(-1), active = actSt[0], setActive = actSt[1];
    var wrapRef = useRef(null), inputRef = useRef(null);
    var size = props.size || "md";
    var listId = id + "-list", labelId = id + "-label";
    var descId = (props.hint || props.error) ? id + "-desc" : undefined;
    useEffect(function () { if (props.defaultQuery) setQuery(props.defaultQuery); }, []);
    useEffect(function () { if (!typing) setQuery(current ? current.label : (props.allowCustom && value != null ? String(value) : "")); }, [value]);
    var filtered = useMemo(function () {
      if (!typing || !query) return options;
      var f = props.filter || function (o, q) { return norm(o.label).indexOf(norm(q)) >= 0 || norm(o.description).indexOf(norm(q)) >= 0; };
      return options.filter(function (o) { return f(o, query); });
    }, [options, query, typing]);
    var customRow = props.allowCustom && typing && query && !options.some(function (o) { return norm(o.label) === norm(query); });
    var list = customRow ? filtered.concat([{ value: query, label: 'Use "' + query + '"', custom: true, icon: "plus" }]) : filtered;
    useOutside(wrapRef, open, function () { commitBlur(); });
    function commitBlur() {
      setOpen(false); setTyping(false);
      if (!props.allowCustom) setQuery(current ? current.label : "");
    }
    function pick(o) {
      var v = o.custom ? query : o.value;
      setValue(v); if (props.onChange) props.onChange(v, o.custom ? null : o);
      setQuery(o.custom ? query : o.label); setTyping(false); setOpen(false);
    }
    function onKey(e) {
      var k = e.key;
      if (k === "ArrowDown") { e.preventDefault(); if (!open) { setOpen(true); setActive(nextEnabled(list, -1, 1)); } else setActive(nextEnabled(list, active, 1)); }
      else if (k === "ArrowUp") { e.preventDefault(); if (open) setActive(nextEnabled(list, active, -1)); }
      else if (k === "Enter") { if (open && list[active]) { e.preventDefault(); pick(list[active]); } }
      else if (k === "Escape") { if (open) { e.preventDefault(); commitBlur(); } else if (query) { setQuery(""); } }
      else if (k === "Tab") { commitBlur(); }
    }
    return h(FieldShell, { label: props.label, hint: props.hint, error: props.error, htmlFor: id, labelId: labelId, descId: descId, required: props.required, className: props.className },
      h("div", { ref: wrapRef, style: { position: "relative" } },
        h("div", { className: cx("lg-inputwrap", size !== "md" && "lg-inputwrap--" + size, props.error && "lg-inputwrap--invalid", props.disabled && "lg-inputwrap--disabled") },
          props.leading ? h("span", { className: "lg-inputwrap__lead" }, renderIcon(props.leading, 18)) : null,
          h("input", {
            id: id, ref: inputRef, className: "lg-input", type: "text", value: query, disabled: props.disabled, name: props.name,
            placeholder: props.placeholder, autoComplete: "off", spellCheck: false,
            role: "combobox", "aria-autocomplete": "list", "aria-expanded": open, "aria-controls": listId,
            "aria-activedescendant": open && active >= 0 ? listId + "-opt-" + active : undefined,
            "aria-invalid": props.error ? true : undefined, "aria-describedby": descId,
            onChange: function (e) { setQuery(e.target.value); setTyping(true); setOpen(true); setActive(e.target.value ? 0 : -1); },
            onFocus: function () { if (props.openOnFocus !== false) setOpen(true); },
            onKeyDown: onKey
          }),
          query && !props.disabled ? h("button", { type: "button", className: "lg-clear", "aria-label": "Clear", onClick: function () {
            setQuery(""); setTyping(true); if (!props.allowCustom) { setValue(undefined); if (props.onChange) props.onChange(undefined, null); } if (inputRef.current) inputRef.current.focus();
          } }, h(Icon, { name: "close-circle", size: 18 })) : null,
          h("button", { type: "button", tabIndex: -1, "aria-label": open ? "Close options" : "Show options", className: cx("lg-chevron", open && "lg-chevron--open"),
            onClick: function () { setOpen(!open); if (inputRef.current) inputRef.current.focus(); } }, h(Icon, { name: "chevron-down", size: 16 }))),
        open ? h(Listbox, {
          id: listId, labelledBy: props.label ? labelId : undefined, options: list, active: active, selected: value, query: typing ? query : "",
          onHover: setActive, onPick: pick, status: list.length ? null : (props.emptyText || "No matches")
        }) : null));
  }

  /* ---------------- SearchBox ---------------- */
  function SearchBox(props) {
    var id = useStableId(props.id, "sb");
    var st = useControlled(props.value, props.defaultValue !== undefined ? props.defaultValue : "");
    var value = st[0], setValue = st[1];
    var focusSt = useState(false), focused = focusSt[0], setFocused = focusSt[1];
    var inputRef = useRef(null);
    var size = props.size || "md";
    function change(v) { setValue(v); if (props.onChange) props.onChange(v); }
    return h("form", {
      role: "search", className: cx("lg-search", props.className), "aria-label": props["aria-label"] || props.placeholder || "Search",
      onSubmit: function (e) { e.preventDefault(); if (props.onSearch) props.onSearch(value); }
    },
      h("div", { className: cx("lg-inputwrap", size !== "md" && "lg-inputwrap--" + size) },
        h("span", { className: "lg-inputwrap__lead" }, h(Icon, { name: "search", size: 18 })),
        h("input", {
          id: id, ref: inputRef, type: "search", className: "lg-input", value: value, autoFocus: props.autoFocus,
          placeholder: props.placeholder || "Search", enterKeyHint: "search", disabled: props.disabled, name: props.name,
          onChange: function (e) { change(e.target.value); },
          onFocus: function () { setFocused(true); }, onBlur: function () { setFocused(false); },
          onKeyDown: function (e) { if (e.key === "Escape" && value) { e.preventDefault(); change(""); } }
        }),
        value ? h("button", { type: "button", className: "lg-clear", "aria-label": "Clear search", onClick: function () { change(""); if (inputRef.current) inputRef.current.focus(); } },
          h(Icon, { name: "close-circle", size: 18 })) : null,
        props.trailing || null),
      props.showCancel && (focused || value) ? h(Button, { variant: "plain", size: size, className: "lg-search__cancel",
        onMouseDown: function (e) { e.preventDefault(); },
        onClick: function () { change(""); if (inputRef.current) inputRef.current.blur(); setFocused(false); if (props.onCancel) props.onCancel(); } }, props.cancelLabel || "Cancel") : null);
  }

  /* ---------------- AsyncSearchBox ---------------- */
  function AsyncSearchBox(props) {
    var id = useStableId(props.id, "as");
    var qSt = useState(props.defaultQuery || ""), query = qSt[0], setQuery = qSt[1];
    var resSt = useState([]), results = resSt[0], setResults = resSt[1];
    var statusSt = useState("idle"), status = statusSt[0], setStatus = statusSt[1]; // idle | loading | done | error
    var errSt = useState(null), err = errSt[0], setErr = errSt[1];
    var openSt = useState(false), open = openSt[0], setOpen = openSt[1];
    var actSt = useState(-1), active = actSt[0], setActive = actSt[1];
    var wrapRef = useRef(null), inputRef = useRef(null), reqRef = useRef(0), ctrlRef = useRef(null), cache = useRef({});
    var debounce = props.debounce != null ? props.debounce : 300, minChars = props.minChars != null ? props.minChars : 1;
    var size = props.size || "md";
    var listId = id + "-list", labelId = id + "-label";
    useOutside(wrapRef, open, function () { setOpen(false); });
    var run = useCallback(function (q) {
      if (ctrlRef.current) ctrlRef.current.abort();
      if (q.trim().length < minChars) { setStatus("idle"); setResults([]); return; }
      if (props.cache !== false && cache.current[q]) { setResults(cache.current[q]); setStatus("done"); setActive(cache.current[q].length ? 0 : -1); return; }
      var my = ++reqRef.current;
      var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null; ctrlRef.current = ctrl;
      setStatus("loading"); setErr(null);
      Promise.resolve().then(function () { return props.loadOptions(q, { signal: ctrl ? ctrl.signal : undefined }); })
        .then(function (res) {
          if (my !== reqRef.current) return; // stale response
          var list = normOptions(res); if (props.cache !== false) cache.current[q] = list;
          setResults(list); setStatus("done"); setActive(list.length ? 0 : -1);
        }, function (e) {
          if (my !== reqRef.current || (e && e.name === "AbortError")) return;
          setErr(e); setStatus("error"); setResults([]);
        });
    }, [props.loadOptions, minChars]);
    useEffect(function () {
      var t = setTimeout(function () { run(query); }, query ? debounce : 0);
      return function () { clearTimeout(t); };
    }, [query]);
    useEffect(function () { if (props.defaultOpen) setOpen(true); return function () { if (ctrlRef.current) ctrlRef.current.abort(); }; }, []);
    function pick(o) {
      if (props.onSelect) props.onSelect(o);
      setQuery(props.keepQueryOnSelect === false ? "" : o.label); setOpen(false);
    }
    function onKey(e) {
      var k = e.key;
      if (k === "ArrowDown") { e.preventDefault(); setOpen(true); setActive(nextEnabled(results, active, 1)); }
      else if (k === "ArrowUp") { e.preventDefault(); setActive(nextEnabled(results, active, -1)); }
      else if (k === "Enter") { e.preventDefault(); if (open && results[active]) pick(results[active]); else if (props.onSubmit) props.onSubmit(query); }
      else if (k === "Escape") { e.preventDefault(); if (open) setOpen(false); else setQuery(""); }
    }
    var msg = null, tone = null, icon = null;
    if (status === "loading" && !results.length) { msg = props.loadingText || "Searching…"; icon = h(Spinner, null); }
    else if (status === "error") { msg = (props.errorText || "Couldn't load results.") + (err && err.message ? " " + err.message : ""); tone = "error"; icon = h(Icon, { name: "error", size: 16 }); }
    else if (status === "done" && !results.length) { msg = props.emptyText ? (typeof props.emptyText === "function" ? props.emptyText(query) : props.emptyText) : 'No results for "' + query + '"'; }
    else if (status === "idle") { msg = minChars > 1 ? "Type at least " + minChars + " characters" : null; }
    var showMenu = open && (results.length || msg);
    var live = status === "loading" ? "Searching" : status === "done" ? results.length + " results" : status === "error" ? "Search failed" : "";
    return h("div", { className: cx("lg-field", props.className) },
      props.label ? h("label", { className: "lg-label", htmlFor: id, id: labelId }, props.label) : null,
      h("div", { ref: wrapRef, role: "search", style: { position: "relative" } },
        h("div", { className: cx("lg-inputwrap", size !== "md" && "lg-inputwrap--" + size), style: { paddingLeft: "var(--space-3)" } },
          h("span", { className: "lg-inputwrap__lead" }, h(Icon, { name: "search", size: 18 })),
          h("input", {
            id: id, ref: inputRef, className: "lg-input", type: "search", value: query, autoComplete: "off", spellCheck: false,
            placeholder: props.placeholder || "Search", disabled: props.disabled, "aria-label": props.label ? undefined : (props.placeholder || "Search"),
            role: "combobox", "aria-autocomplete": "list", "aria-expanded": !!showMenu, "aria-controls": listId, "aria-busy": status === "loading",
            "aria-activedescendant": showMenu && active >= 0 && results.length ? listId + "-opt-" + active : undefined,
            onChange: function (e) { setQuery(e.target.value); setOpen(true); },
            onFocus: function () { setOpen(true); }, onKeyDown: onKey
          }),
          status === "loading" ? h(Spinner, { label: "Searching" }) : null,
          query ? h("button", { type: "button", className: "lg-clear", "aria-label": "Clear search", onClick: function () { setQuery(""); setResults([]); if (inputRef.current) inputRef.current.focus(); } },
            h(Icon, { name: "close-circle", size: 18 })) : null),
        showMenu ? h(Listbox, {
          id: listId, labelledBy: props.label ? labelId : undefined, options: results, active: active, query: query, showCheck: false,
          onHover: setActive, onPick: pick, status: results.length ? null : msg, statusTone: tone, statusIcon: icon
        }) : null,
        h("span", { className: "lg-sr", "aria-live": "polite" }, live)));
  }

  /* ---------------- Checkbox / Radio ---------------- */
  function Checkbox(props) {
    var st = useControlled(props.checked, !!props.defaultChecked);
    var checked = st[0], setChecked = st[1];
    var ref = useRef(null);
    useEffect(function () { if (ref.current) ref.current.indeterminate = !!props.indeterminate; }, [props.indeterminate]);
    var rest = omit(props, ["checked", "defaultChecked", "onChange", "label", "description", "indeterminate", "className"]);
    return h("label", { className: cx("lg-check", props.disabled && "lg-check--disabled", props.className) },
      h("input", assign(rest, { type: "checkbox", ref: ref, checked: checked, onChange: function (e) { setChecked(e.target.checked); if (props.onChange) props.onChange(e.target.checked, e); } })),
      h("span", { className: "lg-check__box", "aria-hidden": true },
        props.indeterminate ? h(Icon, { name: "minus", size: 14, strokeWidth: 3 }) : checked ? h(Icon, { name: "check", size: 14, strokeWidth: 3 }) : null),
      props.label || props.description ? h("span", { className: "lg-check__text" }, props.label,
        props.description ? h("span", { className: "lg-check__desc" }, props.description) : null) : null);
  }
  function RadioGroup(props) {
    var name = useStableId(props.name, "rg");
    var options = normOptions(props.options);
    var st = useControlled(props.value, props.defaultValue);
    var value = st[0], setValue = st[1];
    return h("fieldset", { className: cx("lg-fieldset", props.orientation === "horizontal" && "lg-fieldset--row", props.className), role: "radiogroup" },
      props.label ? h("legend", { className: "lg-legend" }, props.label) : null,
      options.map(function (o) {
        return h("label", { key: String(o.value), className: cx("lg-check lg-check--radio", (o.disabled || props.disabled) && "lg-check--disabled") },
          h("input", { type: "radio", name: name, value: String(o.value), checked: value === o.value, disabled: o.disabled || props.disabled,
            onChange: function () { setValue(o.value); if (props.onChange) props.onChange(o.value, o); } }),
          h("span", { className: "lg-check__box", "aria-hidden": true }, value === o.value ? h("span", { className: "lg-check__dot" }) : null),
          h("span", { className: "lg-check__text" }, o.label, o.description ? h("span", { className: "lg-check__desc" }, o.description) : null));
      }));
  }

  /* ---------------- Switch ---------------- */
  function Switch(props) {
    var id = useStableId(props.id, "sw");
    var st = useControlled(props.checked, !!props.defaultChecked);
    var on = st[0], setOn = st[1];
    var btn = h("button", {
      id: id, type: "button", role: "switch", "aria-checked": on, disabled: props.disabled, className: "lg-switch",
      "aria-label": props.label ? undefined : props["aria-label"], "aria-labelledby": props.label ? id + "-l" : undefined,
      onClick: function () { setOn(!on); if (props.onChange) props.onChange(!on); }
    }, h("span", { className: "lg-switch__knob" }));
    if (!props.label) return btn;
    return h("span", { className: cx("lg-switch-row", props.className) },
      h("span", { id: id + "-l", onClick: function () { if (!props.disabled) { setOn(!on); if (props.onChange) props.onChange(!on); } } }, props.label), btn);
  }

  /* ---------------- Slider ---------------- */
  function Slider(props) {
    var id = useStableId(props.id, "sl");
    var min = props.min != null ? props.min : 0, max = props.max != null ? props.max : 100;
    var st = useControlled(props.value, props.defaultValue != null ? props.defaultValue : (min + max) / 2);
    var v = st[0], setV = st[1];
    var pct = ((v - min) / (max - min)) * 100;
    var fmt = props.format || function (x) { return String(x); };
    return h("div", { className: cx("lg-slider", props.className) },
      props.label || props.showValue ? h("div", { className: "lg-slider__head" },
        h("label", { htmlFor: id }, props.label), props.showValue ? h("span", { className: "lg-slider__value" }, fmt(v)) : null) : null,
      h("input", {
        id: id, type: "range", className: "lg-range", min: min, max: max, step: props.step || 1, value: v, disabled: props.disabled,
        "aria-valuetext": fmt(v), "aria-label": props.label ? undefined : props["aria-label"], style: { "--lg-pct": pct + "%" },
        onChange: function (e) { var n = Number(e.target.value); setV(n); if (props.onChange) props.onChange(n); }
      }));
  }

  /* ---------------- SegmentedControl ---------------- */
  function SegmentedControl(props) {
    var options = normOptions(props.options);
    var st = useControlled(props.value, props.defaultValue !== undefined ? props.defaultValue : (options[0] && options[0].value));
    var value = st[0], setValue = st[1];
    var idx = Math.max(0, options.findIndex(function (o) { return o.value === value; }));
    var refs = useRef([]);
    function sel(i) { var o = options[i]; setValue(o.value); if (props.onChange) props.onChange(o.value, o); if (refs.current[i]) refs.current[i].focus(); }
    function onKey(e) {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); sel((idx + 1) % options.length); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); sel((idx - 1 + options.length) % options.length); }
    }
    return h("div", { role: "radiogroup", "aria-label": props["aria-label"] || props.label, onKeyDown: onKey,
      className: cx("lg-seg lg-glass", props.size === "sm" && "lg-seg--sm", props.className) },
      h("span", { className: "lg-seg__thumb", "aria-hidden": true, style: { width: "calc((100% - 6px) / " + options.length + ")", transform: "translateX(" + idx * 100 + "%)" } }),
      options.map(function (o, i) {
        return h("button", { key: String(o.value), type: "button", role: "radio", "aria-checked": i === idx, tabIndex: i === idx ? 0 : -1,
          ref: function (el) { refs.current[i] = el; }, className: "lg-seg__btn", onClick: function () { sel(i); } }, o.label);
      }));
  }

  /* ---------------- Tabs ---------------- */
  function Tabs(props) {
    var id = useStableId(props.id, "tabs");
    var tabs = props.tabs || [];
    var st = useControlled(props.value, props.defaultValue !== undefined ? props.defaultValue : (tabs[0] && tabs[0].id));
    var value = st[0], setValue = st[1];
    var idx = Math.max(0, tabs.findIndex(function (t) { return t.id === value; }));
    var refs = useRef([]);
    var bottom = props.variant === "bottom";
    function sel(i) { setValue(tabs[i].id); if (props.onChange) props.onChange(tabs[i].id); if (refs.current[i]) refs.current[i].focus(); }
    function onKey(e) {
      var n = tabs.length;
      if (e.key === "ArrowRight") { e.preventDefault(); sel((idx + 1) % n); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); sel((idx - 1 + n) % n); }
      else if (e.key === "Home") { e.preventDefault(); sel(0); }
      else if (e.key === "End") { e.preventDefault(); sel(n - 1); }
    }
    var list = h("div", { role: "tablist", "aria-label": props["aria-label"], onKeyDown: onKey,
      className: cx("lg-tablist lg-glass", bottom && "lg-tablist--bottom lg-glass--float") },
      tabs.map(function (t, i) {
        return h("button", { key: t.id, id: id + "-tab-" + t.id, role: "tab", type: "button", "aria-selected": i === idx, "aria-controls": id + "-panel-" + t.id,
          tabIndex: i === idx ? 0 : -1, ref: function (el) { refs.current[i] = el; },
          className: cx("lg-tab", t.icon && bottom && "lg-tab--icon"), onClick: function () { sel(i); } },
          t.icon ? renderIcon(t.icon, bottom ? 22 : 17) : null, t.label);
      }));
    var cur = tabs[idx];
    var panel = cur && cur.content !== undefined ? h("div", { role: "tabpanel", id: id + "-panel-" + cur.id, "aria-labelledby": id + "-tab-" + cur.id, tabIndex: 0, className: "lg-tabpanel" }, cur.content) : null;
    return h("div", { className: cx("lg-tabs", props.className) }, bottom ? panel : list, bottom ? list : panel);
  }

  /* ---------------- NavBar ---------------- */
  function NavBar(props) {
    var bar = h(Glass, { as: "nav", radius: "capsule", className: "lg-navbar", "aria-label": props["aria-label"] || "Toolbar" },
      h("div", { className: "lg-navbar__side" }, props.leading),
      h("div", { className: "lg-navbar__title" }, props.large ? null : props.title),
      h("div", { className: "lg-navbar__side lg-navbar__side--end" }, props.trailing));
    if (!props.large) return h("div", { className: props.className }, bar);
    return h("header", { className: cx("lg-navbar-large", props.className) }, bar, h("h1", { className: "lg-navbar-large__title" }, props.title));
  }

  /* ---------------- List ---------------- */
  function ListItem(props) {
    var interactive = !!(props.onClick || props.href);
    var inner = [
      props.icon ? h("span", { key: "l", className: "lg-listitem__lead", style: props.iconColor ? { background: props.iconColor } : undefined }, renderIcon(props.icon, 18)) : props.leading ? h("span", { key: "l" }, props.leading) : null,
      h("span", { key: "t", className: "lg-listitem__text" }, h("span", { className: "lg-listitem__title" }, props.title),
        props.subtitle ? h("span", { className: "lg-listitem__sub" }, props.subtitle) : null),
      (props.trailing || props.detail || props.chevron !== false && interactive) ? h("span", { key: "r", className: "lg-listitem__trail" },
        props.detail || null, props.trailing || null, props.chevron !== false && interactive ? h(Icon, { name: "chevron-right", size: 16 }) : null) : null
    ];
    var el = props.href ? h("a", { className: "lg-listitem", href: props.href }, inner)
      : interactive ? h("button", { type: "button", className: "lg-listitem", onClick: props.onClick }, inner)
      : h("div", { className: "lg-listitem" }, inner);
    return h("li", null, el);
  }
  function List(props) {
    return h("section", { className: props.className },
      props.header ? h("div", { className: "lg-list__header" }, props.header) : null,
      h(Glass, { as: "ul", radius: "md", variant: "thick", className: "lg-list" }, props.children));
  }

  /* ---------------- Badge, Progress, Tooltip, Toast, Dialog ---------------- */
  var TONE_ICON = { success: "check-circle", warning: "warning", danger: "error", info: "info" };
  function Badge(props) {
    var tone = props.tone || "neutral";
    return h("span", { className: cx("lg-badge", tone !== "neutral" && "lg-badge--" + tone, props.className) },
      props.icon ? renderIcon(props.icon === true ? TONE_ICON[tone] || "info" : props.icon, 12) : null, props.children);
  }
  function Progress(props) {
    var max = props.max || 100, v = Math.max(0, Math.min(max, props.value || 0));
    var ind = props.indeterminate || props.value == null;
    return h("div", { className: cx("lg-progress", ind && "lg-progress--indeterminate", props.className) },
      props.label || props.showValue ? h("div", { className: "lg-progress__meta" }, h("span", null, props.label), props.showValue && !ind ? h("span", null, Math.round(v / max * 100) + "%") : null) : null,
      h("div", { className: "lg-progress__track", role: "progressbar", "aria-label": props.label || "Progress", "aria-valuemin": 0, "aria-valuemax": max, "aria-valuenow": ind ? undefined : v },
        h("div", { className: "lg-progress__bar", style: ind ? undefined : { width: (v / max * 100) + "%" } })));
  }
  function Tooltip(props) {
    var id = useStableId(null, "tip");
    var st = useState(!!props.defaultOpen), open = st[0], setOpen = st[1];
    var child = React.Children.only(props.children);
    return h("span", { className: "lg-tipwrap", onMouseEnter: function () { setOpen(true); }, onMouseLeave: function () { setOpen(false); },
      onFocus: function () { setOpen(true); }, onBlur: function () { setOpen(false); }, onKeyDown: function (e) { if (e.key === "Escape") setOpen(false); } },
      React.cloneElement(child, { "aria-describedby": open ? id : undefined }),
      open ? h("span", { id: id, role: "tooltip", className: cx("lg-tip lg-glass lg-glass--thick lg-glass--float", props.placement === "bottom" && "lg-tip--bottom") }, props.content) : null);
  }
  function Toast(props) {
    var tone = props.tone || "info";
    return h(Glass, { variant: "thick", radius: "capsule", floating: true, className: cx("lg-toast", props.className), role: tone === "danger" ? "alert" : "status" },
      h("span", { className: "lg-toast__icon lg-toast__icon--" + tone }, h(Icon, { name: TONE_ICON[tone] || "info", size: 22 })),
      h("span", { className: "lg-toast__body" }, h("span", { className: "lg-toast__title" }, props.title),
        props.message ? h("span", { className: "lg-toast__msg" }, props.message) : null),
      props.action || null,
      props.onClose ? h(IconButton, { icon: "close", label: "Dismiss", size: "sm", variant: "plain", onClick: props.onClose }) : null);
  }
  function Dialog(props) {
    var id = useStableId(null, "dlg");
    var ref = useRef(null);
    useEffect(function () {
      if (!props.open) return;
      var prev = document.activeElement;
      var el = ref.current && ref.current.querySelector("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
      if (el && props.autoFocus !== false) el.focus();
      function onKey(e) {
        if (e.key === "Escape" && props.onClose) props.onClose();
        if (e.key === "Tab" && ref.current) {
          var f = ref.current.querySelectorAll("button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
          if (!f.length) return;
          if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
          else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
        }
      }
      document.addEventListener("keydown", onKey);
      return function () { document.removeEventListener("keydown", onKey); if (prev && prev.focus) prev.focus(); };
    }, [props.open]);
    if (!props.open) return null;
    return h("div", { className: cx("lg-overlay", props.inline && "lg-overlay--inline"), onMouseDown: function (e) { if (e.target === e.currentTarget && props.onClose && props.dismissible !== false) props.onClose(); } },
      h("div", { ref: ref, role: props.role || "dialog", "aria-modal": true, "aria-labelledby": id + "-t", className: "lg-dialog lg-glass lg-glass--thick lg-glass--float" },
        h("h2", { id: id + "-t", className: "lg-dialog__title" }, props.title),
        props.children ? h("div", { className: "lg-dialog__body" }, props.children) : null,
        props.actions ? h("div", { className: "lg-dialog__actions" }, props.actions) : null));
  }

  window.Lucent = Object.assign(window.Lucent || {}, {
    Glass: Glass, Card: Card, Button: Button, IconButton: IconButton, Icon: Icon, Spinner: Spinner,
    TextField: TextField, TextArea: TextArea, Select: Select, ComboBox: ComboBox, SearchBox: SearchBox, AsyncSearchBox: AsyncSearchBox,
    Checkbox: Checkbox, RadioGroup: RadioGroup, Switch: Switch, Slider: Slider, SegmentedControl: SegmentedControl,
    Tabs: Tabs, NavBar: NavBar, List: List, ListItem: ListItem,
    Badge: Badge, Progress: Progress, Tooltip: Tooltip, Toast: Toast, Dialog: Dialog,
    utils: { normalize: norm }
  });
})();
