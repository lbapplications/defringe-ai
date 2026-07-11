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
          <div className="timeline">
            {(a?.timeline || []).map((t, i) => {
              const cur = t.startsWith("* ");
              const foc = t.startsWith("~ ");
              const label = cur || foc ? t.slice(2) : t;
              return <div key={i} className={"tl-row" + (cur ? " cur" : "") + (foc ? " foc" : "")}>{label}</div>;
            })}
          </div>
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
