const statusText = document.querySelector("#connection-status");
const checkButton = document.querySelector("#check-connection");

async function checkConnection() {
  checkButton.disabled = true;
  statusText.dataset.state = "pending";
  statusText.textContent = "Checking connection…";

  try {
    const response = await fetch("/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const result = await response.json();
    if (result.status !== "ok") throw new Error("Unexpected health response");

    statusText.dataset.state = "ok";
    statusText.textContent = "Connected. The application is responding.";
  } catch {
    statusText.dataset.state = "error";
    statusText.textContent = "Unable to connect. Check that the app is running and try again.";
  } finally {
    checkButton.disabled = false;
  }
}

checkButton.addEventListener("click", checkConnection);
checkConnection();
