/**
 * Type-resolution shim for react-qr-code@2.1.1.
 *
 * react-qr-code's package.json `exports["."]` map omits a `"types"` condition,
 * so under `moduleResolution: bundler` TypeScript cannot reach the shipped
 * `types/index.d.ts` directly. This file is referenced by the `paths` entry in
 * tsconfig.app.json so TypeScript resolves the module here instead of falling
 * through to a stale global install.
 *
 * Props interface mirrors the package's own shipped declaration at
 * `node_modules/react-qr-code/types/index.d.ts`.
 */

import type * as React from 'react';

export interface QRCodeProps extends React.SVGProps<SVGSVGElement> {
  value: string;
  /** @default 128 */
  size?: number;
  /** @default "#FFFFFF" */
  bgColor?: React.CSSProperties['backgroundColor'];
  /** @default "#000000" */
  fgColor?: React.CSSProperties['color'];
  /** @default "L" */
  level?: 'L' | 'M' | 'H' | 'Q';
  title?: string;
}

declare const QRCode: React.ComponentType<QRCodeProps>;
export default QRCode;
