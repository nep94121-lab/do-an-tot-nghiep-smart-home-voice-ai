(function () {
  "use strict";
  try {
    var params = new URLSearchParams(window.location.search || "");
    if ((params.get("reason") || "").trim().toLowerCase() === "used") {
      document.title = "Mã QR đã được sử dụng · Nhà thông minh";
      var titleEl = document.getElementById("qrExpiredTitle");
      if (titleEl) titleEl.textContent = "Mã QR đã được sử dụng";
      var descEl = document.getElementById("qrExpiredDesc");
      if (descEl) {
        descEl.textContent = "Mã QR này chỉ có hiệu lực cho lần quét đầu tiên và đã được kích hoạt trên thiết bị khác.";
      }
    }
  } catch (e) {}
})();
