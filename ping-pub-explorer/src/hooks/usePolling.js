import { useEffect, useRef } from 'react';
export function usePolling(callback, interval) {
    const cbRef = useRef(callback);
    useEffect(() => {
        cbRef.current = callback;
    }, [callback]);
    useEffect(() => {
        let isCancelled = false;
        const tick = async () => {
            try {
                await cbRef.current();
            }
            catch (error) {
                console.error('Polling error:', error);
            }
            if (!isCancelled) {
                setTimeout(tick, interval);
            }
        };
        tick();
        return () => {
            isCancelled = true;
        };
    }, [interval]);
}
