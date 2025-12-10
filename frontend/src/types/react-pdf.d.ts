declare module "react-pdf" {
  import * as React from "react";

  export const pdfjs: any;

  export interface DocumentProps {
    file: string | Blob | Uint8Array | null;
    className?: string;
    loading?: React.ReactNode;
    error?: React.ReactNode;
    onLoadSuccess?: (pdf: any) => void;
    onLoadError?: (error: any) => void;
    children?: React.ReactNode; 
  }

  // Important: allow children on Document
  export const Document: React.FC<React.PropsWithChildren<DocumentProps>>;

  export interface PageProps {
    pageNumber: number;
    className?: string;
    renderAnnotationLayer?: boolean;
    renderTextLayer?: boolean;
  }

  export const Page: React.FC<PageProps>;
}
