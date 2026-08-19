// app/src/plantiq/web/static/plan.js
//
// Shared room renderer. Knows nothing about the editor: it takes vertices,
// elements and options, and draws. Both the editor and the placement form
// call it, so a change to the drawing shows up in every view at once.

const Plan = (function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const GRID = 20;
  const COLORS = { window: "blue", radiator: "red", air_conditioner: "green" };
  // Plan units, mirrors INSIDE_TOLERANCE in views/plants.py
  const TOLERANCE = 10;

  function element(name, attributes) {
    const node = document.createElementNS(SVG_NS, name);
    for (const key in attributes) node.setAttribute(key, attributes[key]);
    return node;
  }

  function wallCount(vertices, closed) {
    return closed ? vertices.length : Math.max(0, vertices.length - 1);
  }

  function wallAt(vertices, index) {
    const n = vertices.length;
    return [vertices[index], vertices[(index + 1) % n]];
  }

  function wallLength(vertices, index) {
    const [a, b] = wallAt(vertices, index);
    return Math.hypot(b.x - a.x, b.y - a.y);
  }

  function pointOnWall(vertices, index, t) {
    const [a, b] = wallAt(vertices, index);
    return { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) };
  }

  function projectOnWalls(vertices, closed, point) {
    let best = null;
    for (let i = 0; i < wallCount(vertices, closed); i++) {
      const [a, b] = wallAt(vertices, i);
      const dx = b.x - a.x, dy = b.y - a.y;
      const squared = dx * dx + dy * dy;
      if (squared === 0) continue;
      let t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / squared;
      t = Math.max(0, Math.min(1, t));
      const px = a.x + t * dx, py = a.y + t * dy;
      const distance = Math.hypot(point.x - px, point.y - py);
      if (best === null || distance < best.distance) {
        best = { distance, wallIndex: i, t, x: px, y: py };
      }
    }
    return best;
  }

  function polygonArea(vertices) {
    let total = 0;
    const n = vertices.length;
    for (let i = 0; i < n; i++) {
      const a = vertices[i], b = vertices[(i + 1) % n];
      total += a.x * b.y - b.x * a.y;
    }
    return Math.abs(total) / 2;
  }

  // Same half-open rule as engine/geometry.py — the browser must agree with the server
  function pointInPolygon(point, vertices) {
    if (vertices.length < 3) return false;
    let inside = false;
    for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {
      const a = vertices[j], b = vertices[i];
      if ((a.y > point.y) !== (b.y > point.y)) {
        const crossing = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y);
        if (point.x < crossing) inside = !inside;
      }
    }
    return inside;
  }

  function boundingBox(vertices, padding) {
    const xs = vertices.map(v => v.x), ys = vertices.map(v => v.y);
    const minX = Math.min(...xs) - padding, minY = Math.min(...ys) - padding;
    return {
      x: minX, y: minY,
      width: Math.max(...xs) + padding - minX,
      height: Math.max(...ys) + padding - minY,
    };
  }

  function drawGrid(svg, box) {
    const group = element("g", {});
    const startX = Math.floor(box.x / GRID) * GRID;
    const startY = Math.floor(box.y / GRID) * GRID;
    for (let x = startX; x <= box.x + box.width; x += GRID) {
      group.appendChild(element("line", {
        x1: x, y1: box.y, x2: x, y2: box.y + box.height, stroke: "#eee",
      }));
    }
    for (let y = startY; y <= box.y + box.height; y += GRID) {
      group.appendChild(element("line", {
        x1: box.x, y1: y, x2: box.x + box.width, y2: y, stroke: "#eee",
      }));
    }
    svg.appendChild(group);
  }

  /**
   * data    : { vertices, elements, markers }
   * options : { grid, closed, wallLabels, scaleWallIndex, scaleCm,
   *             selectedElement, pending, showVertices, fit }
   */
  function draw(svg, data, options) {
    const vertices = data.vertices || [];
    const elements = data.elements || [];
    const markers = data.markers || [];
    const opts = options || {};
    svg.replaceChildren();

    // fit rescales the drawing to the viewport instead of clipping it
    let box = {
      x: 0, y: 0,
      width: svg.width.baseVal.value,
      height: svg.height.baseVal.value,
    };
    if (opts.fit && vertices.length) {
      box = boundingBox(vertices, 3 * GRID);
      svg.setAttribute("viewBox", `${box.x} ${box.y} ${box.width} ${box.height}`);
    } else {
      svg.removeAttribute("viewBox");
    }

    if (opts.grid) drawGrid(svg, box);

    if (opts.closed && vertices.length > 2) {
      const points = vertices.map(v => `${v.x},${v.y}`).join(" ");
      svg.appendChild(element("polygon", {
        points, fill: "#f5f5f5", stroke: "black", "stroke-width": 2,
      }));
    } else {
      for (let i = 0; i < vertices.length - 1; i++) {
        const a = vertices[i], b = vertices[i + 1];
        svg.appendChild(element("line", {
          x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: "black", "stroke-width": 2,
        }));
      }
    }

    if (opts.wallLabels) {
      for (let i = 0; i < wallCount(vertices, opts.closed); i++) {
        const middle = pointOnWall(vertices, i, 0.5);
        const reference = opts.scaleWallIndex === i;
        svg.appendChild(element("text", {
          x: middle.x, y: middle.y - 4, "font-size": 11,
          "text-anchor": "middle", fill: reference ? "purple" : "#888",
        })).textContent = reference ? `mur ${i} · ${opts.scaleCm} cm` : `mur ${i}`;
      }
    }

    elements.forEach((item, index) => {
      const start = pointOnWall(vertices, item.wall_index, item.t_start);
      const end = pointOnWall(vertices, item.wall_index, item.t_end);
      if (index === opts.selectedElement) {
        svg.appendChild(element("line", {
          x1: start.x, y1: start.y, x2: end.x, y2: end.y,
          stroke: "orange", "stroke-width": 12, "stroke-linecap": "butt",
        }));
      }
      svg.appendChild(element("line", {
        x1: start.x, y1: start.y, x2: end.x, y2: end.y,
        stroke: COLORS[item.type] || "black", "stroke-width": 6, "stroke-linecap": "butt",
        "data-element-index": index, style: "cursor:pointer",
      }));
    });

    if (opts.pending) {
      const point = pointOnWall(vertices, opts.pending.wall_index, opts.pending.t);
      svg.appendChild(element("circle", { cx: point.x, cy: point.y, r: 5, fill: "orange" }));
    }

    markers.forEach((marker, index) => {
      svg.appendChild(element("circle", {
        cx: marker.x, cy: marker.y, r: marker.highlight ? 4 : 3,
        fill: marker.highlight ? "green" : "#4a4", stroke: "black",
        "data-marker-index": index,
        style: marker.draggable ? "cursor:grab" : "",
      }));
      if (marker.label) {
        svg.appendChild(element("text", {
          x: marker.x + 7, y: marker.y + 4, "font-size": 12,
        })).textContent = marker.label;
      }
    });

    if (opts.showVertices) {
      vertices.forEach((vertex, index) => {
        svg.appendChild(element("circle", {
          cx: vertex.x, cy: vertex.y, r: 5, fill: index === 0 ? "black" : "white",
          stroke: "black", "data-index": index,
        }));
      });
    }
  }

  // preserveAspectRatio centres and letterboxes the viewBox, so a plain
  // width ratio is wrong. The screen matrix is the only reliable conversion.
  function mousePoint(svg, event) {
    const point = new DOMPoint(event.clientX, event.clientY);
    const local = point.matrixTransform(svg.getScreenCTM().inverse());
    return { x: local.x, y: local.y };
  }

  function closestOnOutline(point, vertices) {
    let best = null;
    for (let i = 0; i < vertices.length; i++) {
      const a = vertices[i], b = vertices[(i + 1) % vertices.length];
      const dx = b.x - a.x, dy = b.y - a.y;
      const squared = dx * dx + dy * dy;
      let t = squared ? ((point.x - a.x) * dx + (point.y - a.y) * dy) / squared : 0;
      t = Math.max(0, Math.min(1, t));
      const px = a.x + t * dx, py = a.y + t * dy;
      const distance = Math.hypot(point.x - px, point.y - py);
      if (best === null || distance < best.distance) best = { distance, x: px, y: py };
    }
    return best;
  }

  // Free placement, no grid: a plant is not attached to anything. The only
  // constraint is the polygon, and a point just outside slides onto the wall.
  function clampInside(point, vertices) {
    if (pointInPolygon(point, vertices)) return point;
    const closest = closestOnOutline(point, vertices);
    return closest ? { x: closest.x, y: closest.y } : point;
  }

  function pullInside(point, vertices, tolerance) {
    if (pointInPolygon(point, vertices)) return point;
    const closest = closestOnOutline(point, vertices);
    if (closest === null || closest.distance > tolerance) return null;
    return { x: closest.x, y: closest.y };
  }

  return {
    GRID, COLORS, TOLERANCE, element, draw, mousePoint,
    clampInside, pullInside, closestOnOutline,
    wallCount, wallAt, wallLength, pointOnWall, projectOnWalls,
    polygonArea, pointInPolygon,
  };
})();
