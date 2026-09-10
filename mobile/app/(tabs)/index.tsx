import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import * as ImagePicker from "expo-image-picker";

import {
  formatChunkResult,
  runChunkRead,
  type ChunkReadResult,
  type PartSizeMb,
} from "../../spike/chunk-read";

/**
 * Temporary Capture tab body for Phase 2 chunk-read spike.
 * Replace with real capture UI in Phase 8 (and delete mobile/spike/).
 */
export default function CaptureScreen() {
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState("Pick a large gym video, then run 8 MB and 16 MB.");
  const [copied, setCopied] = useState(false);

  async function pickAndRun(partSizeMb: PartSizeMb) {
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["videos"],
      quality: 1,
    });
    if (picked.canceled || !picked.assets[0]?.uri) {
      return;
    }
    setBusy(true);
    setCopied(false);
    setLog(`Running ${partSizeMb} MB parts on ${picked.assets[0].uri} ...`);
    try {
      const result: ChunkReadResult = await runChunkRead(picked.assets[0].uri, partSizeMb);
      const text = formatChunkResult(result);
      const block = `--- ${partSizeMb} MB ---\n${text}`;
      console.log("[chunk-read spike]\n" + block);
      setLog((prev) => {
        const keepPrior = prev.startsWith("---") || prev.includes("uri:") ? `${prev}\n\n` : "";
        return keepPrior + block;
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setLog(`failed: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  async function copyLog() {
    await Clipboard.setStringAsync(log);
    setCopied(true);
    Alert.alert("Copied", "Spike log is on the clipboard. Paste into docs/spikes.md.");
  }

  async function shareLog() {
    await Share.share({ message: log });
  }

  return (
    <View style={styles.root}>
      <Text style={styles.title}>Chunk-read spike</Text>
      <Text style={styles.hint}>
        Phase 2 only. After a run, tap Copy or Share, then paste into docs/spikes.md.
      </Text>
      <View style={styles.row}>
        <Pressable style={styles.button} disabled={busy} onPress={() => pickAndRun(8)}>
          <Text style={styles.buttonText}>Run 8 MB</Text>
        </Pressable>
        <Pressable style={styles.button} disabled={busy} onPress={() => pickAndRun(16)}>
          <Text style={styles.buttonText}>Run 16 MB</Text>
        </Pressable>
      </View>
      <View style={styles.row}>
        <Pressable style={styles.secondary} disabled={busy} onPress={copyLog}>
          <Text style={styles.secondaryText}>{copied ? "Copied" : "Copy log"}</Text>
        </Pressable>
        <Pressable style={styles.secondary} disabled={busy} onPress={shareLog}>
          <Text style={styles.secondaryText}>Share log</Text>
        </Pressable>
      </View>
      {busy ? <ActivityIndicator style={styles.spinner} /> : null}
      <ScrollView style={styles.logBox}>
        <Text style={styles.log} selectable>
          {log}
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, paddingTop: 48, backgroundColor: "#FAF7F2" },
  title: { fontSize: 22, fontWeight: "600", marginBottom: 8 },
  hint: { fontSize: 14, color: "#555", marginBottom: 16 },
  row: { flexDirection: "row", gap: 12, marginBottom: 12 },
  button: {
    backgroundColor: "#3D5C42",
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
  },
  buttonText: { color: "#fff", fontWeight: "600" },
  secondary: {
    borderWidth: 1,
    borderColor: "#3D5C42",
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  secondaryText: { color: "#3D5C42", fontWeight: "600" },
  spinner: { marginVertical: 8 },
  logBox: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#DDD",
    borderRadius: 8,
    padding: 12,
    backgroundColor: "#fff",
  },
  log: { fontFamily: "monospace", fontSize: 12, color: "#111" },
});
