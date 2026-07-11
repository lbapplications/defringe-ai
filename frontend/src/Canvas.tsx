import { useCallback, useEffect, useRef, useState } from "react";
import { Layer, Stage, Transformer } from "react-konva";
import type Konva from "konva";
import AssetNode from "./AssetNode";
import { type Asset, post } from "./state";

type Props = {
  assets: Asset[];
  tool: "move" | "dot";
  showImg: boolean;
  showMask: boolean;
};

// The board view: a Konva stage of assets, back-to-front by server z-order, with a
// Transformer bound to the selected asset for native resize. Drag + resize come from
// Konva itself — no hand-rolled mouse math. Server state (via SSE) is the source of truth;
// gestures POST their result and the stream reconciles.
export default function Canvas({ assets, tool, showImg, showMask }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const nodes = useRef(new Map<string, Konva.Group>());
  const trRef = useRef<Konva.Transformer>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const registerNode = useCallback((name: string, node: Konva.Group | null) => {
    if (node) nodes.current.set(name, node);
    else nodes.current.delete(name);
  }, []);

  const selected = assets.find((a) => a.selected) || null;

  // bind the transformer to the selected asset (resize only in move tool, unlocked)
  useEffect(() => {
    const tr = trRef.current;
    if (!tr) return;
    const node = selected && tool === "move" && !selected.locked ? nodes.current.get(selected.name) : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selected, tool, assets]);

  function onTransformEnd(a: Asset, node: Konva.Group) {
    // display width = baseW * scale; the transformer multiplies it by scaleX, so the new
    // board scale is simply the old one times scaleX. Reset the node's scale (the resized
    // image size is re-derived from a.scale on the next SSE render).
    const scaleX = node.scaleX();
    node.scaleX(1);
    node.scaleY(1);
    post("/api/move", { name: a.name, scale: Math.max(0.15, Math.min(8, a.scale * scaleX)) });
  }

  function onBackgroundClick(e: Konva.KonvaEventObject<MouseEvent>) {
    if (e.target === e.target.getStage()) post("/api/select", { name: "" });
  }

  return (
    <div ref={boxRef} className="stage-box">
      <Stage width={size.w} height={size.h} onMouseDown={onBackgroundClick}>
        <Layer>
          {[...assets]
            .sort((p, q) => p.z - q.z)
            .map((a) => (
              <AssetNode
                key={a.name}
                a={a}
                tool={tool}
                showImg={showImg}
                showMask={showMask}
                onSelect={(name) => post("/api/select", { name })}
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
              const a = assets.find((x) => nodes.current.get(x.name) === g);
              if (a) onTransformEnd(a, g);
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}
