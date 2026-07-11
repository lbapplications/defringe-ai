import { useEffect, useRef } from "react";
import { Circle, Group, Image as KImage, Line, Rect } from "react-konva";
import type Konva from "konva";
import useImage from "use-image";
import { type Asset, dispScale, post } from "./state";

type Props = {
  a: Asset;
  tool: "move" | "dot";
  showImg: boolean;
  showMask: boolean;
  // Optimistic scale held during a resize gesture until the server echoes it back over SSE
  // (see Canvas). When set it overrides a.scale so the image doesn't snap back and wait.
  scaleOverride?: number;
  onSelect: (name: string) => void;
  nodeRef: (name: string, node: Konva.Group | null) => void;
};

// One board asset: the image plus its mask overlay (seed dots + derived outline), all in
// one Konva Group. The group carries position; the image is drawn at its display size and
// mask geometry is mapped image-space -> display-space so dots/outline ride with it.
export default function AssetNode({ a, tool, showImg, showMask, scaleOverride, onSelect, nodeRef }: Props) {
  const [image] = useImage(`/img/${a.name}/${a.head}?v=${encodeURIComponent(a.rev)}`);
  // The edge-map overlay (green edges on transparency) rides on top under the mask view.
  const [edgeImage] = useImage(a.edge ? `/mask/${a.name}?v=${encodeURIComponent(a.edge_rev)}` : "");
  const groupRef = useRef<Konva.Group>(null);

  useEffect(() => {
    nodeRef(a.name, groupRef.current);
    return () => nodeRef(a.name, null);
  }, [a.name, nodeRef]);

  const s = dispScale(a, scaleOverride ?? a.scale);
  const dispW = a.w * s;
  const dispH = a.h * s;
  const draggable = tool === "move" && !a.locked;

  // place a seed dot: pointer -> the group's local (display) space -> image pixels
  function placeDot(e: Konva.KonvaEventObject<MouseEvent>) {
    const grp = groupRef.current;
    if (!grp) return;
    const p = grp.getRelativePointerPosition();
    if (!p) return;
    const x = Math.round(p.x / s);
    const y = Math.round(p.y / s);
    if (x < 0 || y < 0 || x > a.w || y > a.h) return;
    if (!a.selected) post("/api/select", { name: a.name });
    post("/api/dot", { name: a.name, x, y });
    e.cancelBubble = true;
  }

  function onClick(e: Konva.KonvaEventObject<MouseEvent>) {
    if (tool === "dot") return placeDot(e);
    post("/api/select", { name: a.name });
  }

  function onDragEnd(e: Konva.KonvaEventObject<DragEvent>) {
    post("/api/move", { name: a.name, x: Math.round(e.target.x()), y: Math.round(e.target.y()) });
  }

  return (
    <Group
      ref={groupRef}
      x={a.x}
      y={a.y}
      draggable={draggable}
      onMouseDown={() => onSelect(a.name)}
      onClick={onClick}
      onTap={onClick}
      onDragEnd={onDragEnd}
    >
      {/* hit area so clicks land even where the image is transparent */}
      <Rect width={dispW} height={dispH} />
      {showImg && image && <KImage image={image} width={dispW} height={dispH} listening={false} />}
      {showMask && a.edge && edgeImage && (
        <KImage image={edgeImage} width={dispW} height={dispH} listening={false} />
      )}
      {showMask && a.outline.length >= 2 && (
        <Line
          points={a.outline.flatMap(([x, y]) => [x * s, y * s])}
          closed
          stroke="#35ff7d"
          strokeWidth={2}
          fill="#35ff7d22"
          listening={false}
        />
      )}
      {showMask &&
        a.dots.map(([x, y], i) => (
          <Circle
            key={i}
            x={x * s}
            y={y * s}
            radius={5}
            fill="#ff3b6b"
            stroke="#fff"
            strokeWidth={1.5}
            listening={false}
          />
        ))}
    </Group>
  );
}
