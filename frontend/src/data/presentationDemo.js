// Presentation/demo session data used when VITE_DEMO_UI is enabled.
// These records are intentionally synthetic and are not engine verdicts.
// They make the local prototype easy to demonstrate without an empty console.

export const DEMO_UI_MODE = import.meta.env.VITE_DEMO_UI !== 'false';

export const DEMO_CONTRIBUTORS = [
  {
    id: 'vendor-alpha', name: 'Vendor Alpha', type: 'CERTIFIED_VENDOR',
    description: 'Electro-optical systems supplier · Border Surveillance CV Program',
    datasetCount: 2, modelCount: 2
  },
  {
    id: 'vendor-beta', name: 'Vendor Beta', type: 'THIRD_PARTY',
    description: 'Independent AI model and benchmark supplier',
    datasetCount: 1, modelCount: 2
  },
  {
    id: 'vendor-gamma', name: 'Vendor Gamma', type: 'ACADEMIC_RESEARCH',
    description: 'Research partner · Vision assurance reference battery',
    datasetCount: 1, modelCount: 1
  }
];

const HASH_A = '7b9c4d2e1a6f83c2d0b7e1f4a9c6d3e8b5f0a2c7d1e4f8b9c3a6d0e2f7b1c5a';
const HASH_B = 'a31e8c7f42d9b0e6c5f1a8d3b7e2c9f0d4a6b1e8c3f7d2a9b5e0c6f4d1a8b2';

export const DEMO_MODELS = [
  {
    id: 'model-alpha-resnet18-0028', uploadId: 'model-alpha-resnet18-0028',
    name: 'ResNet18 BorderWatch v2.8 · best.pt', originalName: 'best.pt',
    contributorId: 'vendor-alpha', contributorName: 'Vendor Alpha', framework: 'PyTorch',
    size: 46384721, sha256: HASH_A
  },
  {
    id: 'model-alpha-yolo11-0142', uploadId: 'model-alpha-yolo11-0142',
    name: 'YOLO11 EO Detector · production.onnx', originalName: 'production.onnx',
    contributorId: 'vendor-alpha', contributorName: 'Vendor Alpha', framework: 'ONNX',
    size: 28194560, sha256: HASH_B
  },
  {
    id: 'model-beta-trojan-0112', uploadId: 'model-beta-trojan-0112',
    name: 'ResNet18 Backdoor Evaluation · best.pt', originalName: 'best.pt',
    contributorId: 'vendor-beta', contributorName: 'Vendor Beta', framework: 'PyTorch',
    size: 46385102, sha256: 'c82a91f0e7b46d3a5c19f8e2b6047d1a9c53e8f0b2614d7a8e95c3f1b6042a79'
  }
];

export function demoModelsForContributor(id) {
  return DEMO_MODELS.filter((m) => m.contributorId === id);
}

export const DEMO_MODEL_VALIDATION_HISTORY = [
  {
    id: 'VAL-2026-0929-001', modelName: 'ResNet18 BorderWatch v2.8 · best.pt', contributorName: 'Vendor Alpha',
    framework: 'PyTorch', status: 'VALID', computedSha256: HASH_A, validatedAt: '2026-09-29T09:14:22+05:30',
    scope: 'Artifact integrity', note: 'File, format, hash and contributor attribution verified.'
  },
  {
    id: 'VAL-2026-0929-002', modelName: 'ResNet18 Backdoor Evaluation · best.pt', contributorName: 'Vendor Beta',
    framework: 'PyTorch', status: 'VALID', computedSha256: 'c82a91f0e7b46d3a5c19f8e2b6047d1a9c53e8f0b2614d7a8e95c3f1b6042a79',
    validatedAt: '2026-09-29T09:07:41+05:30',
    scope: 'Artifact integrity', note: 'Artifact is intact; behavioural backdoor analysis is performed in Model Integrity.'
  },
  {
    id: 'VAL-2026-0928-017', modelName: 'YOLO11 EO Detector · production.onnx', contributorName: 'Vendor Alpha',
    framework: 'ONNX', status: 'VALID', computedSha256: HASH_B, validatedAt: '2026-09-28T16:42:09+05:30',
    scope: 'Artifact integrity', note: 'ONNX package and registered digest verified.'
  }
];

export const DEMO_INFERENCE_RECORDS = [
  {
    evidenceId: 'seal-7f2a91c8e4b603d1', sealID: 'SEAL-2026-0929-00421',
    timestamp: '2026-09-29T09:31:18.421Z', modelAssetId: 'model-alpha-resnet18-0028',
    modelId: 'model-alpha-resnet18-0028', signatureStatus: 'SEALED',
    evidenceHash: 'e5a9c2d7f14b6380e91a4c2b7d53f8a601c9e4b2d7f5a8c3e1b6d9f2047a5c8'
  },
  {
    evidenceId: 'seal-2d81f5a7c4e903b2', sealID: 'SEAL-2026-0929-00420',
    timestamp: '2026-09-29T09:30:47.109Z', modelAssetId: 'model-alpha-resnet18-0028',
    modelId: 'model-alpha-resnet18-0028', signatureStatus: 'SEALED',
    evidenceHash: '8c1e6a4d9b2f7053c8a1e4d6f0b7c2a9e5d3f1b8c6a4e9d2f7b0c5a1e8d6f3b'
  },
  {
    evidenceId: 'seal-9c42b6e1f7a305d8', sealID: 'SEAL-2026-0929-00419',
    timestamp: '2026-09-29T09:29:55.876Z', modelAssetId: 'model-alpha-yolo11-0142',
    modelId: 'model-alpha-yolo11-0142', signatureStatus: 'SEALED',
    evidenceHash: '3f7a2c9e1b6d4058a4f0c7e2d9b1a6f3c8e5d0b7a2c4f9e1d6b3a8c5e7f0d2a'
  }
];

export const DEMO_PROVENANCE_RUN = {
  runId: 'RUN-INF-2026-0929-00421', status: 'COMPLETED',
  checks: [
    { name: 'INPUT HASH', status: 'PASS', message: 'SHA-256 digest captured and bound to seal.' },
    { name: 'MODEL DIGEST', status: 'PASS', message: 'Registered model digest matches execution asset.' },
    { name: 'CONFIG BINDING', status: 'PASS', message: 'Preprocessing and inference configuration canonicalized.' },
    { name: 'NONCE / REPLAY', status: 'PASS', message: 'Nonce is unique and not present in prior sealed records.' },
    { name: 'ED25519 SIGNATURE', status: 'PASS', message: 'Signature verified against the local assurance key.' }
  ]
};

export const DEMO_DATASETS = [
  { id: 'dataset-alpha-voc2012-500', name: 'VOC2012 BorderWatch · 500-image intake', contributorId: 'vendor-alpha', format: 'YOLO', samples: 500, size: '186.4 MB' },
  { id: 'dataset-beta-integrity-120', name: 'CV Integrity Attack Benchmark · 120 images', contributorId: 'vendor-beta', format: 'COCO', samples: 120, size: '74.8 MB' }
];
