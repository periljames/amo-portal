export const buildInboxQuery = ({ status = "PENDING", page = 1, pageSize = 25 } = {}) => {
  const qs = new URLSearchParams();
  qs.set("status", status);
  qs.set("page", String(page));
  qs.set("page_size", String(pageSize));
  return qs;
};

export const isInboxEmpty = (items) => !items || items.length === 0;
