import { useCallback, useEffect, useRef, useState } from "react";
import { Layer, Stage, Transformer } from "react-konva";
import type Konva from "konva";
import AssetNode from "./AssetNode";
import { type Asset, post } from "./state";

type Props = {
  assets: Asset[];
  select: (session: string) => void;    // optimistic select (App owns the override + POST)
  tool: "move" | "dot";
  showImg: boolean;
  showMask: boolean;
};

// The board view: a Konva stage of assets, back-to-front by server z-order, with a
// Transformer bound to the selected asset for native resize. Drag + resize come from
// Konva itself — no hand-rolled mouse math. Server state (via SSE) is the source of truth;
// gestures POST their result and the stream reconciles.
export default function Canvas({ assets, select, tool, showImg, showMask }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const nodes = useRef(new Map<string, Konva.Group>());
  const trRef = useRef<Konva.Transformer>(null);
  // Optimistic per-asset scale from an in-flight resize: the server round-trips over SSE
  // in up to ~0.4s, so we render the new size immediately and clear each entry once the
  // pushed a.scale catches up. Keeps a stretch smooth instead of snapping back and waiting.
  const [optScale, setOptScale] = useState<Record<string, number>>({});

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const registerNode = useCallback((session: string, node: Konva.Group | null) => {
    if (node) nodes.current.set(session, node);
    else nodes.current.delete(session);
  }, []);

  const selected = assets.find((a) => a.selected) || null;

  // bind the transformer to the selected asset (resize only in move tool, unlocked), and
  // refit its handles when the optimistic size changes (React resizes the child image, but
  // Konva's Transformer needs a nudge to recompute its box around the new bounds).
  useEffect(() => {
    const tr = trRef.current;
    if (!tr) return;
    const node = selected && tool === "move" && !selected.locked ? nodes.current.get(selected.session) : null;
    tr.nodes(node ? [node] : []);
    tr.forceUpdate();
    tr.getLayer()?.batchDraw();
    // Draw again next frame: on a fresh selection the target node may not have painted yet, so
    // the handles' box computes empty and nothing shows until the next redraw (previously: a drag).
    const raf = requestAnimationFrame(() => {
      tr.forceUpdate();
      tr.getLayer()?.batchDraw();
    });
    return () => cancelAnimationFrame(raf);
  }, [selected, tool, assets, optScale]);

  // Drop each optimistic scale once the server's pushed a.scale matches it (gesture landed).
  useEffect(() => {
    setOptScale((m) => {
      let next = m;
      for (const a of assets) {
        if (a.session in m && Math.abs(a.scale - m[a.session]) < 1e-3) {
          if (next === m) next = { ...m };
          delete next[a.session];
        }
      }
      return next;
    });
  }, [assets]);

  function onTransformEnd(a: Asset, node: Konva.Group) {
    // display width = baseW * scale; the transformer multiplies the current display size by
    // scaleX, so the new board scale is the current one times scaleX. Reset the node's own
    // scale to 1 and hold the result optimistically (optScale) so the image shows the new
    // size right away — it's re-derived from a.scale once the SSE echo arrives.
    const scaleX = node.scaleX();
    node.scaleX(1);
    node.scaleY(1);
    const base = optScale[a.session] ?? a.scale;
    const next = Math.max(0.15, Math.min(8, base * scaleX));
    setOptScale((m) => ({ ...m, [a.session]: next }));
    post("/api/move", { session: a.session, scale: next });
  }

  function onBackgroundClick(e: Konva.KonvaEventObject<MouseEvent>) {
    if (e.target === e.target.getStage()) select("");
  }

  return (
    <div ref={boxRef} className="stage-box">
      <Stage width={size.w} height={size.h} onMouseDown={onBackgroundClick}>
        <Layer>
          {[...assets]
            .sort((p, q) => p.z - q.z)
            .map((a) => (
              <AssetNode
                key={a.session}
                a={a}
                tool={tool}
                showImg={showImg}
                showMask={showMask}
                scaleOverride={optScale[a.session]}
                select={select}
                nodeRef={registerNode}
              />
            ))}
          <Transformer
            ref={trRef}
            rotateEnabled={false}
            keepRatio
            enabledAnchors={["top-left", "top-right", "bottom-left", "bottom-right"]}
            boundBoxFunc={(oldBox, newBox) => (newBox.width < 30 ? oldBox : newBox)}
            onTransformEnd={(e) => {
              const g = e.target as Konva.Group;
              const a = assets.find((x) => nodes.current.get(x.session) === g);
              if (a) onTransformEnd(a, g);
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}
