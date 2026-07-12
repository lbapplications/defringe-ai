import { useEffect, useState } from "react";
import Canvas from "./Canvas";
import Toolbox from "./Toolbox";
import { post, useBoard } from "./state";

// Thin shell: owns the client-only UI state (active tool + view toggles), subscribes to
// the board over SSE, and composes the toolbox (controls) with the canvas (view). All
// board/edit state lives on the server; this component holds none of it.
export default function App() {
  const assets = useBoard();
  const [tool, setTool] = useState<"move" | "dot">("move");
  const [showImg, setShowImg] = useState(true);
  const [showMask, setShowMask] = useState(true);

  // keyboard undo/redo on the selected asset (Ctrl/Cmd+Z, +Shift for redo)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      const a = assets.find((x) => x.selected);
      if (!a) return;
      if (e.shiftKey && a.can_redo) post("/api/redo", { session: a.session });
      else if (!e.shiftKey && a.can_undo) post("/api/undo", { session: a.session });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assets]);

  return (
    <>
      <header>
        <b>defringe-ai</b> · edit screen
        <a href="/chains">edit chains →</a>
        <span className="hint">drag to move · corner handles to resize · Dot tool to seed · pushed live</span>
      </header>
      <Toolbox
        assets={assets}
        tool={tool}
        setTool={setTool}
        showImg={showImg}
        setShowImg={setShowImg}
        showMask={showMask}
        setShowMask={setShowMask}
      />
      <main className={"stage-wrap" + (tool === "dot" ? " tool-dot" : "")}>
        <Canvas assets={assets} tool={tool} showImg={showImg} showMask={showMask} />
      </main>
    </>
  );
}
