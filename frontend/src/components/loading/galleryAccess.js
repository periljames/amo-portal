export const isLoaderGalleryEnabled = ({ isAdmin, isProd, flag }) => {
  if (!isAdmin) return false;
  if (!isProd) return true;
  return flag === "1";
};
