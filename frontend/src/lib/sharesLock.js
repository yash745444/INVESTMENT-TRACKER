export const isSharesUnlocked = () => sessionStorage.getItem("shares_unlocked") === "1";
export const setSharesUnlocked = () => sessionStorage.setItem("shares_unlocked", "1");
