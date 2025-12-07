import { useEffect, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Box, Eye, EyeOff } from 'lucide-react';
import { imagingAPI } from '@/services/api';
import { useViewerStore } from '@/store/useViewerStore';
import type { VolumeData } from '@/types';

interface VolumeRenderProps {
  volumeData: VolumeData;
  opacity: number;
}

function VolumeRender({ volumeData, opacity }: VolumeRenderProps) {
  const groupRef = useRef<THREE.Group>(null);
  const [sliceMeshes, setSliceMeshes] = useState<THREE.Mesh[]>([]);

  useFrame(() => {
    if (groupRef.current) {
      // Slow rotation for better visualization
      groupRef.current.rotation.y += 0.005;
    }
  });

  useEffect(() => {
    const [depth, height, width] = volumeData.shape;
    const meshes: THREE.Mesh[] = [];

    // Create a slice every N slices to avoid too many planes
    const step = Math.max(1, Math.floor(depth / 20)); // Show ~20 slices

    for (let z = 0; z < depth; z += step) {
      // Create canvas for this slice
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');

      if (ctx) {
        const imageData = ctx.createImageData(width, height);
        const data = imageData.data;

        // Fill imageData with slice data
        for (let y = 0; y < height; y++) {
          for (let x = 0; x < width; x++) {
            const value = volumeData.volume[z][y][x];
            const index = (y * width + x) * 4;
            data[index] = value;     // R
            data[index + 1] = value; // G
            data[index + 2] = value; // B
            data[index + 3] = value > 10 ? 255 : 0; // A - transparency for low values
          }
        }

        ctx.putImageData(imageData, 0, 0);

        // Create texture from canvas
        const texture = new THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;

        // Create mesh for this slice
        const geometry = new THREE.PlaneGeometry(2, 2);
        const material = new THREE.MeshBasicMaterial({
          map: texture,
          transparent: true,
          opacity: opacity,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);

        // Position slice along Z axis
        const normalizedZ = (z / depth) * 2 - 1; // Map to -1 to 1
        mesh.position.z = normalizedZ;

        meshes.push(mesh);
      }
    }

    setSliceMeshes(meshes);

    // Cleanup
    return () => {
      meshes.forEach(mesh => {
        mesh.geometry.dispose();
        if (mesh.material instanceof THREE.Material) {
          mesh.material.dispose();
        }
      });
    };
  }, [volumeData, opacity]);

  return (
    <group ref={groupRef}>
      {sliceMeshes.map((mesh, i) => (
        <primitive key={i} object={mesh} />
      ))}
    </group>
  );
}

export default function ImageViewer3D() {
  const { t } = useTranslation();
  const [opacity, setOpacity] = useState(0.8);
  const [showWireframe, setShowWireframe] = useState(false);
  const [renderMode, setRenderMode] = useState<'interactive' | 'voxel'>('interactive');
  const [voxelAngle, setVoxelAngle] = useState(320);
  const { currentSeries, orientation } = useViewerStore();

  // Fetch 3D volume data for interactive mode
  const { data: volumeData, isLoading } = useQuery({
    queryKey: ['volume', currentSeries?.file_id, orientation],
    queryFn: () =>
      currentSeries && currentSeries.file_id
        ? imagingAPI.get3DVolume(currentSeries.file_id, orientation)
        : null,
    enabled: !!(currentSeries && currentSeries.file_id && renderMode === 'interactive'),
  });

  // Fetch voxel visualization for static mode
  const { data: voxelData, isLoading: voxelLoading } = useQuery({
    queryKey: ['voxel-3d', currentSeries?.file_id, voxelAngle],
    queryFn: () =>
      currentSeries && currentSeries.file_id
        ? imagingAPI.getVoxel3D(currentSeries.file_id, undefined, undefined, voxelAngle)
        : null,
    enabled: !!(currentSeries && currentSeries.file_id && renderMode === 'voxel'),
  });

  if (!currentSeries) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-800">
        <div className="text-center text-gray-400">
          <Box className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.selectImageFor3D')}</p>
        </div>
      </div>
    );
  }

  if (!currentSeries.file_id) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-800">
        <div className="text-center text-gray-400">
          <Box className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.noFileId')}</p>
          <p className="text-sm mt-2">{t('viewer.tryReload')}</p>
        </div>
      </div>
    );
  }

  if (isLoading || voxelLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-800">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <p>{t('viewer.loading3D')} {renderMode === 'voxel' ? t('viewer.voxelVisualization') : t('viewer.volumeVisualization')}...</p>
          <p className="text-sm text-gray-400 mt-2">{t('viewer.takesTime')}</p>
        </div>
      </div>
    );
  }

  if (renderMode === 'interactive' && !volumeData) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-800">
        <div className="text-center text-gray-400">
          <Box className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.not3DAvailable')}</p>
          <p className="text-sm mt-2">{t('viewer.volumeDataNotLoaded')}</p>
          <button
            onClick={() => setRenderMode('voxel')}
            className="mt-4 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
          >
            {t('viewer.tryVoxelView')}
          </button>
        </div>
      </div>
    );
  }

  if (renderMode === 'voxel' && !voxelData) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-800">
        <div className="text-center text-gray-400">
          <Box className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.voxelNotAvailable')}</p>
          <p className="text-sm mt-2">{t('viewer.voxelDataNotLoaded')}</p>
          <button
            onClick={() => setRenderMode('interactive')}
            className="mt-4 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
          >
            {t('viewer.tryInteractiveView')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full bg-black">
      {renderMode === 'voxel' && voxelData ? (
        <div className="flex items-center justify-center h-full p-4">
          <img
            src={voxelData.image}
            alt="3D Voxel Visualization"
            className="max-w-full max-h-full object-contain"
          />
        </div>
      ) : volumeData ? (
        <Canvas>
          <PerspectiveCamera makeDefault position={[3, 3, 3]} />
          <OrbitControls enableDamping dampingFactor={0.05} />

          {/* Lighting */}
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} />
          <directionalLight position={[-10, -10, -5]} intensity={0.5} />

          {/* Volume */}
          <VolumeRender volumeData={volumeData} opacity={opacity} />

          {/* Grid helper */}
          <gridHelper args={[10, 10]} />
          <axesHelper args={[2]} />
        </Canvas>
      ) : null}

      {/* Controls Panel */}
      <div className="absolute top-4 right-4 bg-gray-900 bg-opacity-90 rounded-lg p-4 space-y-4 w-64">
        {/* Render Mode Toggle */}
        <div>
          <label className="block text-sm text-gray-300 mb-2">{t('viewer.renderMode')}</label>
          <div className="flex gap-2">
            <button
              onClick={() => setRenderMode('interactive')}
              className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                renderMode === 'interactive'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {t('viewer.interactive')}
            </button>
            <button
              onClick={() => setRenderMode('voxel')}
              className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                renderMode === 'voxel'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {t('viewer.voxel')}
            </button>
          </div>
        </div>

        {renderMode === 'interactive' && (
          <>
            <div>
              <label className="block text-sm text-gray-300 mb-2">{t('viewer.opacity')}</label>
              <input
                type="range"
                min="0"
                max="100"
                value={opacity * 100}
                onChange={(e) => setOpacity(parseFloat(e.target.value) / 100)}
                className="w-full"
              />
              <div className="text-xs text-gray-400 mt-1">
                {(opacity * 100).toFixed(0)}%
              </div>
            </div>

            <button
              onClick={() => setShowWireframe(!showWireframe)}
              className="w-full flex items-center justify-between px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded transition-colors text-sm text-white"
            >
              <span>{t('viewer.wireframe')}</span>
              {showWireframe ? (
                <Eye className="w-4 h-4" />
              ) : (
                <EyeOff className="w-4 h-4" />
              )}
            </button>
          </>
        )}

        {renderMode === 'voxel' && (
          <div>
            <label className="block text-sm text-gray-300 mb-2">{t('viewer.viewAngle')}</label>
            <input
              type="range"
              min="0"
              max="360"
              value={voxelAngle}
              onChange={(e) => setVoxelAngle(parseInt(e.target.value))}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              {voxelAngle}°
            </div>
          </div>
        )}
      </div>

      {/* Info Panel */}
      {volumeData && renderMode === 'interactive' && (
        <div className="absolute top-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-300 space-y-1">
          <div>{t('viewer.mode')}: {t('viewer.interactive')}</div>
          <div>{t('viewer.orientation')}: {orientation}</div>
          <div>
            {t('viewer.dimensions')}: {volumeData.shape[0]} x {volumeData.shape[1]} x{' '}
            {volumeData.shape[2]}
          </div>
          <div>{t('viewer.modality')}: {volumeData.metadata.modality || 'N/A'}</div>
        </div>
      )}

      {renderMode === 'voxel' && (
        <div className="absolute top-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-300 space-y-1">
          <div>{t('viewer.mode')}: {t('viewer.voxel')}</div>
          <div>{t('viewer.viewAngle')}: {voxelAngle}°</div>
        </div>
      )}

      {/* Instructions */}
      {renderMode === 'interactive' && (
        <div className="absolute bottom-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-400">
          <div>{t('viewer.instructions.leftClick')}</div>
          <div>{t('viewer.instructions.rightClick')}</div>
          <div>{t('viewer.instructions.scroll')}</div>
        </div>
      )}

      {renderMode === 'voxel' && (
        <div className="absolute bottom-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2 text-xs text-gray-400">
          <div>{t('viewer.instructions.adjustAngle')}</div>
          <div>{t('viewer.instructions.tryAngles')}</div>
        </div>
      )}
    </div>
  );
}
