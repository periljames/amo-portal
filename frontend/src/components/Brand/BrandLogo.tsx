import React from "react";
import { BrandMark } from "./BrandMark";

type BrandLogoProps = {
  size?: number;
  className?: string;
};

export const BrandLogo: React.FC<BrandLogoProps> = ({ size = 36, className }) => {
  return <BrandMark size={size} className={className} />;
};
