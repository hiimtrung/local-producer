// An image file from the server (works when the server needs a token).
import { useFileUrl } from "../../hooks/useFileUrl";

export interface ServerImageProps {
  url: string | null;
  alt: string;
  className?: string;
  lazy?: boolean;
}

export function ServerImage({ url, alt, className, lazy }: ServerImageProps) {
  const src = useFileUrl(url);
  if (!src) return null;
  return <img className={className} src={src} alt={alt} loading={lazy ? "lazy" : undefined} />;
}
