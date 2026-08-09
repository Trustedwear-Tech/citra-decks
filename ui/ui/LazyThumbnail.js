/**
 * LazyThumbnail - Intersection Observer based lazy image loader for web.
 *
 * Problem: When the presentation/printable/report list modals open, all visible
 * thumbnail images (S3 presigned URLs) fire simultaneously. Browsers cap concurrent
 * connections per domain at ~6 (HTTP/1.1), so the overflow causes TCP resets
 * (net::ERR_CONNECTION_RESET).
 *
 * Solution: Only start loading the <img> when the card scrolls into the viewport,
 * and auto-retry once on network error (covers transient S3 connection resets).
 */
import React, { useRef, useState, useEffect, useCallback } from 'react';
import { View, Image, Platform, ActivityIndicator } from 'react-native';

const RETRY_DELAY_MS = 1500; // retry after 1.5 s
const MAX_RETRIES = 2;

/**
 * @param {object} props
 * @param {string}  props.uri           – Image URL (S3 presigned or any HTTPS)
 * @param {object}  props.style         – Style applied to <Image>
 * @param {string}  [props.resizeMode]  – e.g. 'cover'
 * @param {function} [props.onError]    – Called when all retries exhausted
 * @param {React.ReactNode} props.placeholder – What to show before/during load
 * @param {string}  [props.rootMargin]  – IntersectionObserver rootMargin (default '200px')
 */
const LazyThumbnail = ({
    uri,
    style,
    resizeMode = 'cover',
    onError,
    placeholder,
    rootMargin = '200px',
}) => {
    const containerRef = useRef(null);
    const [isVisible, setIsVisible] = useState(false);
    const [retryCount, setRetryCount] = useState(0);
    const [imageKey, setImageKey] = useState(0); // force remount on retry
    const [failed, setFailed] = useState(false);
    const retryTimerRef = useRef(null);

    // ---- Intersection Observer (web only) ----
    useEffect(() => {
        if (Platform.OS !== 'web' || !uri) {
            setIsVisible(true); // On native, load immediately (RN FlatList handles virtualization)
            return;
        }

        const node = containerRef.current;
        if (!node) {
            setIsVisible(true);
            return;
        }

        if (typeof IntersectionObserver === 'undefined') {
            setIsVisible(true); // Fallback for old browsers
            return;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setIsVisible(true);
                    observer.disconnect(); // Once visible, stop observing
                }
            },
            { rootMargin } // Start loading 200px before entering viewport
        );

        observer.observe(node);

        return () => {
            observer.disconnect();
            if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
        };
    }, [uri, rootMargin]);

    // ---- Handle load error with auto-retry ----
    const handleError = useCallback(() => {
        if (retryCount < MAX_RETRIES) {
            // Retry after a short delay
            retryTimerRef.current = setTimeout(() => {
                setRetryCount(prev => prev + 1);
                setImageKey(prev => prev + 1); // Force remount to re-fetch
            }, RETRY_DELAY_MS * (retryCount + 1)); // Progressive delay: 1.5s, 3s
        } else {
            setFailed(true);
            if (onError) onError();
        }
    }, [retryCount, onError]);

    // Reset state when URI changes
    useEffect(() => {
        setRetryCount(0);
        setImageKey(0);
        setFailed(false);
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    }, [uri]);

    // ---- Render ----
    if (!uri || failed) {
        return placeholder || null;
    }

    // Wrapper div for the IntersectionObserver ref
    if (Platform.OS === 'web') {
        return (
            <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
                {isVisible ? (
                    <Image
                        key={imageKey}
                        source={{ uri }}
                        style={style}
                        resizeMode={resizeMode}
                        onError={handleError}
                    />
                ) : (
                    // Lightweight placeholder while waiting to enter viewport
                    placeholder || (
                        <View style={[style, { justifyContent: 'center', alignItems: 'center' }]}>
                            <ActivityIndicator size="small" color="#999" />
                        </View>
                    )
                )}
            </div>
        );
    }

    // Native: load immediately (FlatList virtualisation handles offscreen)
    return (
        <Image
            key={imageKey}
            source={{ uri }}
            style={style}
            resizeMode={resizeMode}
            onError={handleError}
        />
    );
};

export default React.memo(LazyThumbnail);
