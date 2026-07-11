import { useState } from "react";
import { type Asset, post } from "./state";

type Props = {
  assets: Asset[];
  tool: "move" | "dot";
  setTool: (t: "move" | "dot") => void;
  showImg: boolean;
  setShowImg: (v: boolean) => void;
  showMask: boolean;
  setShowMask: (v: boolean) => void;
};

// The controls: pick an interaction tool, toggle what's visible, and drive the selected
// asset's mask/history actions. Every button POSTs to the backend through state.post — the
// toolbox never holds board state itself; it reads the pushed asset list and reflects it.
export default function Toolbox({
  assets,
  tool,
  setTool,
  showImg,
  setShowImg,
  showMask,
  setShowMask,
}: Props) {
  const a = assets.find((x) => x.selected) || null;
  const dots = a ? a.dots.length : 0;
  const act = (url: string) => a && post(url, { name: a.name });
  const derive = (op: string, params: object) => a && post("/api/derive", { name: a.name, op, ...params });
  // Derive-tool slider params — adjust, then click the op to apply with these values.
  const [lo, setLo] = useState(100);
  const [hi, setHi] = useState(200);
  const [radius, setRadius] = useState(2);
  const [maxLink, setMaxLink] = useState(100);
  const [keep, setKeep] = useState(1);
  const timeline = a?.timeline || [];
  const headIdx = Math.max(0, timeline.findIndex((t) => t.startsWith("* ")));

  return (
    <aside id="tools">
      <div className="tools-head">Tools</div>
      <div className="tools-body">
        <Group label="Tool">
          <div className="btn-row">
            <button className={"tool-btn" + (tool === "move" ? " active" : "")} onClick={() => setTool("move")}>
              ✋ Move
            </button>
            <button className={"tool-btn" + (tool === "dot" ? " active" : "")} onClick={() => setTool("dot")}>
              • Dot
            </button>
          </div>
        </Group>

        <Group label="View">
          <div className="btn-row">
            <button className={"tool-btn" + (showImg ? "" : " off")} onClick={() => setShowImg(!showImg)}>
              👁 Image
            </button>
            <button className={"tool-btn" + (showMask ? "" : " off")} onClick={() => setShowMask(!showMask)}>
              👁 Mask
            </button>
          </div>
        </Group>

        <Group label="Selected image">
          <div className="sel-name">{a ? a.name : "— none —"}</div>
          <button
            className={"wide-btn" + (a?.locked ? " on" : "")}
            disabled={!a}
            onClick={() => a && post("/api/lock", { name: a.name, locked: !a.locked })}
          >
            {a?.locked ? "🔒 Unlock image" : "🔓 Lock image"}
          </button>
        </Group>

        <Group label="History">
          <div className="btn-row">
            <button className="tool-btn" disabled={!a?.can_undo} onClick={() => act("/api/undo")} title="Ctrl+Z">
              ↶ Undo
            </button>
            <button className="tool-btn" disabled={!a?.can_redo} onClick={() => act("/api/redo")} title="Ctrl+Shift+Z">
              ↷ Redo
            </button>
          </div>
          <select
            className="history-select"
            disabled={!a || timeline.length === 0}
            value={headIdx}
            onChange={(e) => a && post("/api/history/goto", { name: a.name, index: Number(e.target.value) })}
          >
            {timeline.map((t, i) =>
              t.startsWith("~ ") ? null : (
                <option key={i} value={i}>
                  {i}. {t.startsWith("* ") ? t.slice(2) : t}
                </option>
              ),
            )}
          </select>
          <button className="wide-btn" disabled={!a} onClick={() => act("/api/reset")} title="revert to the original image and wipe this image's history">
            ⟲ Reset image
          </button>
        </Group>

        <Group label="Derive · edge map">
          <Slider label="Canny lo" value={lo} min={0} max={255} set={setLo} />
          <Slider label="Canny hi" value={hi} min={0} max={255} set={setHi} />
          <button className="wide-btn" disabled={!a} onClick={() => derive("edge", { lo, hi })}>
            ▚ Edge (Canny → mask)
          </button>

          <Slider label="Close radius" value={radius} min={1} max={12} set={setRadius} />
          <Slider label="Bridge max-link" value={maxLink} min={5} max={200} set={setMaxLink} />
          <div className="btn-row">
            <button
              className="tool-btn"
              disabled={!a || !a.edge}
              title="morphological closing: dilate → erode (bloats, seals small gaps)"
              onClick={() => derive("close", { radius })}
            >
              ⬤ Close
            </button>
            <button
              className="tool-btn"
              disabled={!a || !a.edge}
              title="graph nearest-neighbour link: thin 1px bridges, no bloat"
              onClick={() => derive("bridge", { max_link: maxLink })}
            >
              ⤳ Bridge
            </button>
          </div>
          <div className="muted">Close/Bridge transform the current overlay — run Edge first.</div>

          <Slider label="Keep N shapes" value={keep} min={1} max={8} set={setKeep} />
          <button
            className="wide-btn"
            disabled={!a || !a.edge}
            title="connected-components filter: keep the N largest shapes, drop the rest (noise)"
            onClick={() => derive("keep", { keep })}
          >
            ◇ Keep largest (drop noise)
          </button>
        </Group>

        <Group label="Mask">
          <div className="muted">{dots} dot{dots === 1 ? "" : "s"}</div>
          <button className="wide-btn" disabled={!a || dots < 3} onClick={() => act("/api/connect")}>
            Connect dots (hull → snap)
          </button>
          <button
            className="wide-btn"
            disabled={!a || !(a.outline.length >= 3)}
            onClick={() => act("/api/isolate")}
          >
            Cut out (fill mask → alpha)
          </button>
          <button className="wide-btn" disabled={!a || dots === 0} onClick={() => act("/api/dots/clear")}>
            Clear dots
          </button>
        </Group>
      </div>
    </aside>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="tool-group">
      <div className="grp-label">{label}</div>
      {children}
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  set,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  set: (v: number) => void;
}) {
  return (
    <label className="slider-row">
      <span className="slider-label">
        {label}
        <b>{value}</b>
      </span>
      <input type="range" min={min} max={max} value={value} onChange={(e) => set(Number(e.target.value))} />
    </label>
  );
}
