import { StyleSheet, Text, View } from "react-native";

type Props = { title: string };

// Stand-in screen body until each tab gets real content in later phases.
export function Placeholder({ title }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20 },
});
