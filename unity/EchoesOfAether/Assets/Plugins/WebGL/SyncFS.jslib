mergeInto(LibraryManager.library, {
  // Flush persistentDataPath (IDBFS) to IndexedDB so saves survive a closed tab.
  EOA_SyncFS: function () {
    if (typeof FS !== 'undefined' && FS.syncfs) FS.syncfs(false, function (err) { if (err) console.warn('[save] syncfs failed', err); });
  },
});
