const ext = typeof browser !== "undefined" ? browser : chrome;

function sendMessage(message) {
  return new Promise((resolve) => {
    try {
      ext.runtime.sendMessage(message, (response) => resolve(response || { ok: false }));
    } catch {
      resolve({ ok: false });
    }
  });
}

const input = document.getElementById("api-url");
const saveBtn = document.getElementById("save");
const saved = document.getElementById("saved");

(async () => {
  const config = await sendMessage({ action: "trustguard-get-config" });
  input.value = config?.apiBase || "http://localhost:5000/api/v1";
})();

saveBtn.addEventListener("click", async () => {
  await sendMessage({ action: "trustguard-set-config", apiBaseUrl: input.value.trim() });
  saved.style.display = "block";
  setTimeout(() => (saved.style.display = "none"), 1500);
});