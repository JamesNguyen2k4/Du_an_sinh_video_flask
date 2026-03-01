// static/js/app.js

async function api(url, opts = {}) {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data?.error || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }
  
  async function uploadFile(jobId, kind, file) {
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    return api(`/api/jobs/${jobId}/upload`, { method: "POST", body: fd });
  }
  
  function qs(id) { return document.querySelector(id); }
  
  function setText(el, txt) { if (el) el.textContent = txt; }
  function setHTML(el, html) { if (el) el.innerHTML = html; }
  
  function storeJobId(jobId) {
    localStorage.setItem("lecture_job_id", jobId);
  }
  function loadJobId() {
    return localStorage.getItem("lecture_job_id");
  }
  
  // ---------- INDEX PAGE ----------
  async function initIndexPage() {
    const btnNext = qs("#btn-next");               // nút "Tiếp tục"
    if (!btnNext) return; // không phải index page
  
    const status = qs("#status");
    const voiceMode = qs("#voice_mode");          // select/radio
    const imgInput = qs("#source_image");         // <input type="file">
    const pptxInput = qs("#pptx");                // <input type="file">
  
    // builtin inputs
    const langInput = qs("#audio_language");      // select
    const genderInput = qs("#gender");            // select
    const builtinVoiceInput = qs("#builtin_voice"); // optional select
  
    // clone inputs
    const cloneMp3Input = qs("#voice_sample");    // <input type="file">
    const cloneBtn = qs("#btn-clone");            // nút "Tạo giọng clone"
    const cloneSelect = qs("#cloned_voice_name"); // select
    const clonedLang = qs("#cloned_lang");        // select
  
    let jobId = loadJobId();
  
    async function createNewJob() {
      const created = await api("/api/jobs", { method: "POST" });
      jobId = created.job_id;
      storeJobId(jobId);
      return jobId;
    }
    
    async function refreshCloneList() {
      const data = await api("/api/voices/cloned");
      if (cloneSelect) {
        cloneSelect.innerHTML = `<option value="">-- Chọn giọng --</option>` +
          data.voices.map(v => `<option value="${v}">${v}</option>`).join("");
      }
    }
  
    if (cloneBtn) {
      cloneBtn.addEventListener("click", async () => {
        try {
          await ensureJob();
          const f = cloneMp3Input?.files?.[0];
          if (!f) throw new Error("Chưa chọn file mp3 giọng mẫu");
          setText(status, "Đang upload mp3...");
          await uploadFile(jobId, "voice_sample", f);
  
          setText(status, "Đang clone giọng...");
          const fd = new FormData();
          // có thể không cần attach file vì server lấy từ voice_sample đã upload
          const out = await fetch(`/api/jobs/${jobId}/clone-voice`, { method: "POST", body: fd });
          const data = await out.json();
          if (!out.ok || !data.ok) throw new Error(data?.error || "clone failed");
  
          await refreshCloneList();
          if (cloneSelect && data.display_name) cloneSelect.value = data.display_name;
  
          setText(status, `✅ Đã tạo giọng clone: ${data.display_name}`);
        } catch (e) {
          setText(status, `❌ ${e.message}`);
        }
      });
    }
  
    // load clone list sẵn
    refreshCloneList().catch(() => {});
    async function refreshBuiltinVoices() {
      const lang = langInput?.value || "vi";
      const gender = genderInput?.value || "Nữ";
    
      // gọi API backend để lấy list voice theo lang + gender
      const data = await api(`/api/voices/builtin?lang=${encodeURIComponent(lang)}&gender=${encodeURIComponent(gender)}`);
    
      if (!builtinVoiceInput) return;
    
      const voices = data.voices || [];
      builtinVoiceInput.innerHTML =
        `<option value="">-- Tự chọn theo giọng đọc (${gender}) --</option>` +
        voices.map(v => {
          // v.id là voice shortName (ex: vi-VN-NamMinhNeural)
          // v.name là tên hiển thị
          const label = v.name ? `${v.name} (${v.id})` : v.id;
          return `<option value="${v.id}">${label}</option>`;
        }).join("");
    }
    
    // gọi 1 lần lúc load trang
    refreshBuiltinVoices().catch(() => {});
    
    // lắng nghe thay đổi
    langInput?.addEventListener("change", () => refreshBuiltinVoices().catch(() => {}));
    genderInput?.addEventListener("change", () => refreshBuiltinVoices().catch(() => {}));
  
    btnNext.addEventListener("click", async () => {
      try {
        await createNewJob()
  
        const img = imgInput?.files?.[0];
        const pptx = pptxInput?.files?.[0];
        if (!img) throw new Error("Chưa chọn ảnh giáo viên");
        if (!pptx) throw new Error("Chưa chọn file PPTX");
  
        setText(status, "Đang upload ảnh...");
        await uploadFile(jobId, "source_image", img);
  
        setText(status, "Đang upload PPTX...");
        await uploadFile(jobId, "pptx", pptx);
  
        const vm = (voiceMode?.value || "builtin");
        const normalized = (vm.toLowerCase().includes("nhân") || vm === "clone") ? "clone" : "builtin";
  
        const cfg = {
          voice_mode: normalized,
          language: langInput?.value || "vi",
          gender: genderInput?.value || "Nữ",
          builtin_voice: builtinVoiceInput?.value || null,
          cloned_voice_name: cloneSelect?.value || null,
          cloned_lang: clonedLang?.value || null,
        };
  
        setText(status, "Đang lưu cấu hình...");
        await api(`/api/jobs/${jobId}/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cfg),
        });
  
        setText(status, "Đang trích xuất slide...");
        await api(`/api/jobs/${jobId}/extract`, { method: "POST" });
  
        // sang editor
        window.location.href = `/editor?job=${encodeURIComponent(jobId)}`;
      } catch (e) {
        setText(status, `❌ ${e.message}`);
      }
    });
  }
  
  // ---------- EDITOR PAGE ----------
  async function initEditorPage() {
    const editor = qs("#slides_text");            // textarea
    if (!editor) return;
  
    const btnExtract = qs("#btn-extract");        // optional
    const btnSave = qs("#btn-save");
    const btnGenerate = qs("#btn-generate");
    const status = qs("#status");
  
    const jobId = new URLSearchParams(window.location.search).get("job") || loadJobId();
    if (!jobId) {
      setText(status, "❌ Không có job_id");
      return;
    }
    storeJobId(jobId);
  
    async function loadSlides() {
      setText(status, "Đang tải nội dung slide...");
      const cfg = await api(`/api/jobs/${jobId}/config`);
      // nếu bạn muốn hiển thị config ở UI editor thì dùng cfg ở đây
  
      // lấy slides_text từ storage: hiện API chưa có GET slides-text, nên cách nhanh:
      // gọi /extract lại để lấy slides_text
      const ex = await api(`/api/jobs/${jobId}/extract`, { method: "POST" });
      editor.value = ex.slides_text || "";
      setText(status, "✅ Đã tải nội dung slide");
    }
  
    if (btnExtract) {
      btnExtract.addEventListener("click", () => loadSlides().catch(e => setText(status, `❌ ${e.message}`)));
    }
  
    if (btnSave) {
      btnSave.addEventListener("click", async () => {
        try {
          setText(status, "Đang lưu...");
          await api(`/api/jobs/${jobId}/slides-text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slides_text: editor.value || "" }),
          });
          setText(status, "✅ Đã lưu");
        } catch (e) {
          setText(status, `❌ ${e.message}`);
        }
      });
    }
  
    if (btnGenerate) {
      btnGenerate.addEventListener("click", async () => {
        try {
          setText(status, "Đang enqueue job...");
          await api(`/api/jobs/${jobId}/slides-text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slides_text: editor.value || "" }),
          });
  
          const out = await api(`/api/jobs/${jobId}/generate`, { method: "POST" });
          setText(status, `✅ Đã chạy job (${out.job_id || jobId}). Đang xử lý...`);
  
          // poll status
          const poll = async () => {
            const st = await api(`/api/jobs/${jobId}/status`);
            if (st.state === "done") {
              setText(status, "✅ Hoàn thành! Đang chuyển sang trang kết quả...");
              window.location.href = `/result?job=${encodeURIComponent(jobId)}`;
              return;
            }
            if (st.state === "failed") {
              setText(status, `❌ Thất bại: ${st.message || ""}`);
              return;
            }
            const msg = st.message || `Processing ${st.current || 0}/${st.total || 0}`;
            setText(status, msg);
            setTimeout(poll, 1500);
          };
          poll();
        } catch (e) {
          setText(status, `❌ ${e.message}`);
        }
      });
    }
  
    loadSlides().catch(e => setText(status, `❌ ${e.message}`));
  }
  
  // ---------- RESULT PAGE ----------
  async function initResultPage() {
    const video = qs("#final_video");             // <video>
    const btnDownload = qs("#btn-download");      // <a> or button
    const status = qs("#status");
    if (!video && !btnDownload) return;
  
    const jobId = new URLSearchParams(window.location.search).get("job") || loadJobId();
    if (!jobId) {
      setText(status, "❌ Không có job_id");
      return;
    }
  
    // poll status đến khi done
    const poll = async () => {
      const st = await api(`/api/jobs/${jobId}/status`);
      if (st.state === "done") {
        setText(status, st.message || "✅ Done");
        const viewUrl = `/media/jobs/${jobId}/video`;       // xem trực tiếp
        const dlUrl   = `/api/jobs/${jobId}/result`;       // tải về (attachment)

        if (video) video.src = viewUrl;

        if (btnDownload) {
        if (btnDownload.tagName.toLowerCase() === "a") btnDownload.href = dlUrl;
        else btnDownload.addEventListener("click", () => window.open(dlUrl, "_blank"));
        }

        return;
      }
      if (st.state === "failed") {
        setText(status, `❌ ${st.message || "failed"}`);
        return;
      }
      setText(status, st.message || "Đang xử lý...");
      setTimeout(poll, 1500);
    };
    poll().catch(e => setText(status, `❌ ${e.message}`));
  }
  
  document.addEventListener("DOMContentLoaded", () => {
    initIndexPage();
    initEditorPage();
    initResultPage();
  });
  