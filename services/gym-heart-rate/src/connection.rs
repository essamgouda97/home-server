//! Notification silence is not evidence of a broken Bluetooth connection.
use anyhow::{ensure, Context, Result};
use futures_util::{Stream, StreamExt};
use std::{future::Future, time::Duration};

pub async fn next_connected<S, C, F>(stream: &mut S, mut connected: C) -> Result<S::Item>
where
    S: Stream + Unpin,
    C: FnMut() -> F,
    F: Future<Output = Result<bool>>,
{
    loop {
        match tokio::time::timeout(Duration::from_secs(2), stream.next()).await {
            Ok(notification) => return notification.context("Bluetooth notification stream ended"),
            Err(_) => {
                // Keep the approved subscription during measurement gaps or phone approval.
                // Only an actual disconnect/error should trigger a new connection.
                let active = tokio::time::timeout(Duration::from_secs(5), connected()).await??;
                ensure!(active, "Bluetooth disconnected");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::stream;

    #[tokio::test(start_paused = true)]
    async fn silence_beyond_both_old_deadlines_preserves_the_stream() {
        let (tx, rx) = tokio::sync::mpsc::channel(1);
        let task = tokio::spawn(async move {
            let mut source = Box::pin(stream::unfold(rx, |mut rx| async {
                rx.recv().await.map(|item| (item, rx))
            }));
            next_connected(&mut source, || async { Ok(true) }).await
        });
        tokio::task::yield_now().await;
        for _ in 0..60 {
            tokio::time::advance(Duration::from_secs(2)).await;
            tokio::task::yield_now().await;
            assert!(
                !task.is_finished(),
                "Silence must not end a healthy session"
            );
        }
        tx.send(42).await.unwrap();
        assert_eq!(task.await.unwrap().unwrap(), 42);
    }

    #[tokio::test(start_paused = true)]
    async fn actual_disconnect_ends_the_session() {
        let mut source = stream::pending::<u8>();
        assert!(next_connected(&mut source, || async { Ok(false) })
            .await
            .is_err());
    }

    #[tokio::test]
    async fn closed_notification_stream_ends_the_session() {
        let mut source = stream::empty::<u8>();
        assert!(next_connected(&mut source, || async { Ok(true) })
            .await
            .is_err());
    }

    #[tokio::test(start_paused = true)]
    async fn unresponsive_connection_check_is_bounded() {
        let mut source = stream::pending::<u8>();
        assert!(
            next_connected(&mut source, || std::future::pending::<Result<bool>>())
                .await
                .is_err()
        );
    }
}
