import { useEffect } from 'react';
import { useUserTracking } from '../context/UserTrackingContext';

export const useTracking = (product) => {
  const { trackProductView, trackProductTimeSpent } = useUserTracking();

  useEffect(() => {
    if (product) {
      trackProductView(product);

      const startTime = Date.now();
      return () => {
        const secondsSpent = Math.round((Date.now() - startTime) / 1000);
        if (secondsSpent > 1) {
          trackProductTimeSpent(product.id, secondsSpent);
        }
      };
    }
  }, [product]);
};
