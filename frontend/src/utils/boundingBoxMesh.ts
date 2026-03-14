import { NVMeshUtilities } from '@niivue/niivue';
import type { LesionBoundingBox } from '@/types';

type Vec3 = [number, number, number];

/** Transform 8 bbox corners from voxel space to mm via NIfTI affine */
function voxelCornersToMM(bbox: LesionBoundingBox, affine: number[][]): Vec3[] {
  const voxCorners: Vec3[] = [
    [bbox.x_min, bbox.y_min, bbox.z_min], // 0: bottom-front-left
    [bbox.x_max, bbox.y_min, bbox.z_min], // 1: bottom-front-right
    [bbox.x_min, bbox.y_max, bbox.z_min], // 2: bottom-back-left
    [bbox.x_max, bbox.y_max, bbox.z_min], // 3: bottom-back-right
    [bbox.x_min, bbox.y_min, bbox.z_max], // 4: top-front-left
    [bbox.x_max, bbox.y_min, bbox.z_max], // 5: top-front-right
    [bbox.x_min, bbox.y_max, bbox.z_max], // 6: top-back-left
    [bbox.x_max, bbox.y_max, bbox.z_max], // 7: top-back-right
  ];

  return voxCorners.map(([x, y, z]) => [
    affine[0][0] * x + affine[0][1] * y + affine[0][2] * z + affine[0][3],
    affine[1][0] * x + affine[1][1] * y + affine[1][2] * z + affine[1][3],
    affine[2][0] * x + affine[2][1] * y + affine[2][2] * z + affine[2][3],
  ]);
}

/** Normalize a 3D vector in-place, returns length */
function normalize(v: Vec3): number {
  const len = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (len > 1e-10) {
    v[0] /= len;
    v[1] /= len;
    v[2] /= len;
  }
  return len;
}

/** Cross product a x b */
function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/**
 * Generate a tube (cylinder without endcaps) between two points.
 * Appends vertices and triangle indices to the provided arrays.
 */
function makeTube(
  vertices: number[],
  indices: number[],
  start: Vec3,
  end: Vec3,
  radius: number,
  sides: number = 6,
): void {
  const dir: Vec3 = [end[0] - start[0], end[1] - start[1], end[2] - start[2]];
  const len = normalize(dir);
  if (len < 1e-10) return; // degenerate edge

  // Find a perpendicular vector
  let perp1: Vec3;
  if (Math.abs(dir[0]) < 0.9) {
    perp1 = cross(dir, [1, 0, 0]);
  } else {
    perp1 = cross(dir, [0, 1, 0]);
  }
  normalize(perp1);
  const perp2 = cross(dir, perp1);
  normalize(perp2);

  const baseIndex = vertices.length / 3;

  // Generate two rings of vertices
  for (let ring = 0; ring < 2; ring++) {
    const center = ring === 0 ? start : end;
    for (let i = 0; i < sides; i++) {
      const angle = (2 * Math.PI * i) / sides;
      const cos = Math.cos(angle) * radius;
      const sin = Math.sin(angle) * radius;
      vertices.push(
        center[0] + perp1[0] * cos + perp2[0] * sin,
        center[1] + perp1[1] * cos + perp2[1] * sin,
        center[2] + perp1[2] * cos + perp2[2] * sin,
      );
    }
  }

  // Triangulate the cylinder wall
  for (let i = 0; i < sides; i++) {
    const i0 = baseIndex + i;
    const i1 = baseIndex + ((i + 1) % sides);
    const i2 = baseIndex + sides + i;
    const i3 = baseIndex + sides + ((i + 1) % sides);
    // Two triangles per quad
    indices.push(i0, i2, i1);
    indices.push(i1, i2, i3);
  }
}

/** The 12 edges of a box defined by corner indices 0-7 */
const BOX_EDGES: [number, number][] = [
  // Bottom face (z_min)
  [0, 1], [2, 3], [0, 2], [1, 3],
  // Top face (z_max)
  [4, 5], [6, 7], [4, 6], [5, 7],
  // Vertical edges
  [0, 4], [1, 5], [2, 6], [3, 7],
];

/**
 * Create an MZ3 ArrayBuffer containing a wireframe bounding box mesh.
 * The box is defined by the lesion's bounding box in voxel space,
 * transformed to mm via the NIfTI affine matrix.
 */
export function createBoundingBoxMZ3(
  bbox: LesionBoundingBox,
  affine: number[][],
  tubeRadius: number = 0.5,
): ArrayBuffer {
  const corners = voxelCornersToMM(bbox, affine);

  const vertices: number[] = [];
  const indices: number[] = [];

  for (const [a, b] of BOX_EDGES) {
    makeTube(vertices, indices, corners[a], corners[b], tubeRadius);
  }

  const verts = new Float32Array(vertices);
  const tris = new Uint32Array(indices);

  return NVMeshUtilities.createMZ3(verts, tris, false);
}
