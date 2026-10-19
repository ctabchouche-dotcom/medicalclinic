(function () {
    const app = document.querySelector(".clinic-app");
    if (!app) {
        return;
    }

    const toast = app.querySelector(".clinic-toast");

    function showToast(message) {
        if (!toast) {
            window.alert(message);
            return;
        }
        toast.textContent = message;
        toast.hidden = false;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(function () {
            toast.hidden = true;
        }, 4000);
    }

    document.querySelectorAll("[data-open]").forEach(function (button) {
        button.addEventListener("click", function () {
            const dialog = document.getElementById(button.dataset.open);
            if (dialog && dialog.showModal) {
                dialog.showModal();
            }
        });
    });

    document.querySelectorAll("dialog").forEach(function (dialog) {
        dialog.querySelectorAll(".js-close").forEach(function (button) {
            button.addEventListener("click", function () {
                dialog.close();
            });
        });
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                dialog.close();
            }
        });
    });

    if (app.dataset.open) {
        const dialog = document.getElementById(app.dataset.open);
        if (dialog && dialog.showModal) {
            dialog.showModal();
        }
    }

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params: params,
            }),
        }).then(function (response) {
            return response.json().then(function (payload) {
                if (!response.ok || payload.error) {
                    const data = (payload.error && payload.error.data) || {};
                    throw new Error(data.message || (payload.error && payload.error.message) || "Action impossible.");
                }
                return payload.result;
            });
        });
    }

    let dragged = null;

    document.querySelectorAll(".clinic-grip").forEach(function (grip) {
        grip.addEventListener("dragstart", function (event) {
            const card = grip.closest(".clinic-card");
            dragged = card;
            card.classList.add("is-dragging");
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", JSON.stringify({
                model: card.dataset.model,
                id: card.dataset.id,
                moves: card.dataset.moves || "",
            }));
        });
        grip.addEventListener("dragend", function () {
            if (dragged) {
                dragged.classList.remove("is-dragging");
            }
            dragged = null;
            document.querySelectorAll(".clinic-column.is-over").forEach(function (column) {
                column.classList.remove("is-over");
            });
        });
    });

    document.querySelectorAll(".clinic-column").forEach(function (column) {
        column.addEventListener("dragover", function (event) {
            event.preventDefault();
            column.classList.add("is-over");
        });
        column.addEventListener("dragleave", function () {
            column.classList.remove("is-over");
        });
        column.addEventListener("drop", function (event) {
            event.preventDefault();
            column.classList.remove("is-over");
            let payload;
            try {
                payload = JSON.parse(event.dataTransfer.getData("text/plain") || "{}");
            } catch (error) {
                return;
            }
            const target = column.dataset.state;
            const moves = (payload.moves || "").split(",").filter(Boolean);
            if (!payload.id || !target || moves.indexOf(target) === -1) {
                showToast("Ce déplacement n'est pas autorisé.");
                return;
            }
            rpc("/clinic/kanban/move", {
                model: payload.model,
                res_id: Number(payload.id),
                state: target,
                role: app.dataset.role,
            }).then(function () {
                window.location.reload();
            }).catch(function (error) {
                showToast(error.message || "Action impossible.");
            });
        });
    });

    const medFilter = document.querySelector("[data-med-filter]");
    const medSelect = document.querySelector("[data-med-select]");
    if (medFilter && medSelect) {
        const options = Array.from(medSelect.options);
        medFilter.addEventListener("input", function () {
            const query = medFilter.value.trim().toLowerCase();
            options.forEach(function (option) {
                if (!option.value) {
                    option.hidden = false;
                    return;
                }
                const haystack = (option.dataset.search || option.textContent || "").toLowerCase();
                option.hidden = Boolean(query) && haystack.indexOf(query) === -1;
            });
        });
    }
})();
